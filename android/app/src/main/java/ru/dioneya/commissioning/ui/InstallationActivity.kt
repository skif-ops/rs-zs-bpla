package ru.dioneya.commissioning.ui

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ru.dioneya.commissioning.R
import ru.dioneya.commissioning.ble.AndroidBleTransport
import ru.dioneya.commissioning.core.CoordinateSource
import ru.dioneya.commissioning.core.InstallationCommissioningRole
import ru.dioneya.commissioning.core.PhoneLocationProvider
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.position.InstallationScreenController
import java.util.concurrent.Executors

/**
 * "Координаты установки" (ICD §3.1): reads the stored record, fills the fields from the
 * phone fix or the keyboard, writes INITIAL / RECOMMISSION, reads back and verifies.
 * Requires [EXTRA_DEVICE_ADDRESS]; the trust policy is shown but editable only in the
 * service-engineer role.
 */
class InstallationActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private var session: BleSession? = null
    private var controller: InstallationScreenController? = null
    private lateinit var status: TextView
    private lateinit var details: TextView
    private lateinit var lat: EditText
    private lateinit var lon: EditText
    private lateinit var alt: EditText
    private lateinit var acc: EditText
    private var source = CoordinateSource.MANUAL
    private var role = InstallationCommissioningRole.INSTALLER
    private lateinit var location: PhoneLocationProvider

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        location = PhoneLocationProvider(this)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }
        val serial = intent.getStringExtra(EXTRA_STATION_SERIAL).orEmpty()
        root.addView(TextView(this).apply { text = getString(R.string.install_title, serial); textSize = 22f })
        fun num(hint: Int, value: String) = EditText(this).apply {
            this.hint = getString(hint); setText(value)
            inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED
        }
        lat = num(R.string.install_latitude, ""); lon = num(R.string.install_longitude, "")
        alt = num(R.string.install_altitude, "0"); acc = num(R.string.install_accuracy, "5")
        root.addView(lat); root.addView(lon); root.addView(alt); root.addView(acc)
        val sourceButton = Button(this).apply { text = getString(R.string.install_source, source.name) }
        sourceButton.setOnClickListener {
            source = when (source) { CoordinateSource.MANUAL -> CoordinateSource.SURVEYED; CoordinateSource.SURVEYED -> CoordinateSource.MANUAL; else -> CoordinateSource.MANUAL }
            sourceButton.text = getString(R.string.install_source, source.name)
        }
        root.addView(sourceButton)
        val roleButton = Button(this).apply { text = getString(R.string.install_role, role.name) }
        roleButton.setOnClickListener {
            role = if (role == InstallationCommissioningRole.INSTALLER) InstallationCommissioningRole.SERVICE_ENGINEER else InstallationCommissioningRole.INSTALLER
            roleButton.text = getString(R.string.install_role, role.name); controller?.setRole(role)
        }
        root.addView(roleButton)
        val useLocation = Button(this).apply { text = getString(R.string.install_use_phone_location) }
        val read = Button(this).apply { text = getString(R.string.install_read) }
        val apply = Button(this).apply { text = getString(R.string.install_apply) }
        root.addView(useLocation); root.addView(read); root.addView(apply)
        status = TextView(this).apply { textSize = 16f; setPadding(0, pad, 0, 0) }
        details = TextView(this).apply { textSize = 13f; setPadding(0, pad / 2, 0, 0) }
        root.addView(status); root.addView(details)
        setContentView(ScrollView(this).apply { addView(root) })

        val address = intent.getStringExtra(EXTRA_DEVICE_ADDRESS).orEmpty()
        val device = if (BluetoothAdapter.checkBluetoothAddress(address)) (getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter?.getRemoteDevice(address) else null
        if (device == null) { status.text = getString(R.string.server_no_device); read.isEnabled = false; apply.isEnabled = false }
        val transport = device?.let { AndroidBleTransport(this, it) }
        val s = BleSession(transport ?: NoTransport)
        session = s
        controller = InstallationScreenController(s, { System.currentTimeMillis() * 1000L }) { st -> runOnUiThread { render(st) } }.also { c ->
            c.connectedProbe = { transport?.isConnected ?: false }
        }

        useLocation.setOnClickListener {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(arrayOf(Manifest.permission.ACCESS_FINE_LOCATION), REQUEST_LOCATION); return@setOnClickListener
            }
            status.text = getString(R.string.install_waiting_fix)
            location.requestSingleLocation { loc ->
                runOnUiThread {
                    if (loc == null) status.text = getString(R.string.install_no_fix)
                    else controller?.useLocation(location.toInstallationPosition(loc))
                }
            }
        }
        read.setOnClickListener { executor.execute { controller?.readStored() } }
        apply.setOnClickListener { controller?.edit(readFields()); executor.execute { controller?.apply() } }
        if (device != null) executor.execute { controller?.readStored() }
    }

    private fun readFields() = InstallationScreenController.Fields(
        latitude = lat.text.toString(), longitude = lon.text.toString(), altitudeM = alt.text.toString(), accuracyM = acc.text.toString(),
        source = source, policy = controller?.state?.fields?.policy ?: ru.dioneya.commissioning.core.PositionTrustPolicy(),
    )

    private fun render(st: InstallationScreenController.State) {
        if (st.fields.source == CoordinateSource.PHONE_LOCATION && lat.text.toString() != st.fields.latitude) {
            lat.setText(st.fields.latitude); lon.setText(st.fields.longitude); alt.setText(st.fields.altitudeM); acc.setText(st.fields.accuracyM)
            source = CoordinateSource.PHONE_LOCATION
        }
        status.text = when (st.phase) {
            InstallationScreenController.Phase.IDLE, InstallationScreenController.Phase.EDITING -> st.message
            InstallationScreenController.Phase.READING -> getString(R.string.install_reading)
            InstallationScreenController.Phase.INVALID -> getString(R.string.server_invalid, st.errors.joinToString(", "))
            InstallationScreenController.Phase.WRITING -> getString(R.string.install_writing, st.operation.name)
            InstallationScreenController.Phase.READING_BACK -> getString(R.string.server_reading_back)
            InstallationScreenController.Phase.VERIFIED -> getString(R.string.install_verified, st.message)
            InstallationScreenController.Phase.MISMATCH -> getString(R.string.install_mismatch, st.errors.joinToString(", "))
            InstallationScreenController.Phase.REJECTED, InstallationScreenController.Phase.ERROR -> st.message
        }
        details.text = buildString {
            (st.readback ?: st.stored)?.let { rb ->
                append("lat ").append(rb.position.latE7 / 1e7).append("  lon ").append(rb.position.lonE7 / 1e7)
                append("  alt ").append(rb.position.altDm / 10.0).append(" m  ±").append(rb.position.accuracyM).append(" m  ")
                append(rb.position.source.name.lowercase()).append("  v").append(rb.position.version).append('\n')
                append("policy ").append(rb.policy.warningDistanceM).append('/').append(rb.policy.suspectDistanceM).append('/').append(rb.policy.grossJumpDistanceM)
                append(" m, ").append(rb.policy.warningConsecutiveFixes).append('/').append(rb.policy.suspectConsecutiveFixes).append(" fixes\n")
                append("generation ").append(rb.storageGeneration).append("  hash ").append(rb.commissioningHashHex.take(16)).append("…  audit ").append(rb.auditCommitted).append('\n')
            }
        }
        details.visibility = if (details.text.isEmpty()) View.GONE else View.VISIBLE
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.execute { try { session?.run({ session?.disconnect() }, 3000) } catch (_: Exception) {} }
        executor.shutdown()
        session?.close()
    }

    private object NoTransport : ru.dioneya.commissioning.core.ble.BleTransport {
        override fun connect(timeoutMs: Long): Int = throw ru.dioneya.commissioning.core.ble.BleException("no station selected", ru.dioneya.commissioning.core.ble.BleError.NOT_FOUND)
        override fun disconnect() {}
        override val isConnected: Boolean get() = false
        override fun write(characteristic: java.util.UUID, value: ByteArray, timeoutMs: Long) = connect(0).let {}
        override fun read(characteristic: java.util.UUID, timeoutMs: Long): ByteArray = connect(0).let { ByteArray(0) }
        override fun setNotifications(characteristic: java.util.UUID, enabled: Boolean, timeoutMs: Long) = connect(0).let {}
        override fun setNotificationSink(sink: ru.dioneya.commissioning.core.ble.BleTransport.NotificationSink?) {}
    }

    companion object {
        const val EXTRA_DEVICE_ADDRESS = ServerActivity.EXTRA_DEVICE_ADDRESS
        const val EXTRA_STATION_SERIAL = ServerActivity.EXTRA_STATION_SERIAL
        private const val REQUEST_LOCATION = 45
    }
}
