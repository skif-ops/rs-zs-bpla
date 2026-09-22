package ru.dioneya.commissioning.ui

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.text.InputType
import android.view.View
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ru.dioneya.commissioning.ble.AndroidBleTransport
import ru.dioneya.commissioning.core.SimSlot
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.profile.ServerProfile
import ru.dioneya.commissioning.core.profile.ServerProfileStore
import ru.dioneya.commissioning.ble.PreferencesServerProfileStore
import ru.dioneya.commissioning.core.server.ServerScreenController
import java.util.concurrent.Executors

/**
 * "Сервер" screen: MQTT/TLS endpoint fields -> CBOR patch over BLE -> read-back
 * verification -> optional self-test.  Classic views only (no Compose, no Play
 * services), all BLE work on a background executor, UI updated on the main thread.
 * The station MAC comes from the intent extra [EXTRA_DEVICE_ADDRESS] (scanner/QR
 * flow lands in a later step); an empty address shows the fields in validate-only mode.
 */
class ServerActivity : Activity() {
    private val executor = Executors.newSingleThreadExecutor()
    private var session: BleSession? = null
    private var controller: ServerScreenController? = null
    private lateinit var status: TextView
    private lateinit var details: TextView
    private lateinit var inputs: Map<String, EditText>
    private var simSlot = SimSlot.SIM1
    private lateinit var profiles: ServerProfileStore

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }
        val serial = intent.getStringExtra(EXTRA_STATION_SERIAL).orEmpty()
        root.addView(TextView(this).apply {
            text = if (serial.isEmpty()) getString(ru.dioneya.commissioning.R.string.server_title) else getString(ru.dioneya.commissioning.R.string.server_title_for, serial)
            textSize = 22f
        })
        profiles = PreferencesServerProfileStore(this)
        val saved = profiles.load()
        val defaults = (saved?.toFields() ?: ServerScreenController.Fields()).copy(tenant = intent.getStringExtra(EXTRA_TENANT).orEmpty())
        simSlot = defaults.preferredSim
        val specs = listOf(
            "hostPort" to (getString(ru.dioneya.commissioning.R.string.server_host_port) to defaults.hostPort),
            "httpsPort" to (getString(ru.dioneya.commissioning.R.string.server_https_port) to defaults.httpsPort),
            "caReference" to (getString(ru.dioneya.commissioning.R.string.server_ca_reference) to defaults.caReference),
            "fingerprintHex" to (getString(ru.dioneya.commissioning.R.string.server_fingerprint) to defaults.fingerprintHex),
            "tenant" to (getString(ru.dioneya.commissioning.R.string.server_tenant) to defaults.tenant),
            "topicPrefix" to (getString(ru.dioneya.commissioning.R.string.server_topic_prefix) to defaults.topicPrefix),
            "version" to (getString(ru.dioneya.commissioning.R.string.server_version) to defaults.version),
            "apn1" to (getString(ru.dioneya.commissioning.R.string.server_apn1) to defaults.apn1),
            "apn2" to (getString(ru.dioneya.commissioning.R.string.server_apn2) to defaults.apn2),
        )
        inputs = specs.associate { (key, spec) ->
            val e = EditText(this).apply {
                hint = spec.first; setText(spec.second)
                inputType = if (key == "httpsPort" || key == "version") InputType.TYPE_CLASS_NUMBER else InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS
            }
            root.addView(e)
            key to e
        }
        val simButton = Button(this).apply { text = getString(ru.dioneya.commissioning.R.string.server_sim, simSlot.name) }
        simButton.setOnClickListener {
            simSlot = if (simSlot == SimSlot.SIM1) SimSlot.SIM2 else SimSlot.SIM1
            simButton.text = getString(ru.dioneya.commissioning.R.string.server_sim, simSlot.name)
        }
        root.addView(simButton)
        val apply = Button(this).apply { text = getString(ru.dioneya.commissioning.R.string.server_apply) }
        val selfTest = Button(this).apply { text = getString(ru.dioneya.commissioning.R.string.server_self_test) }
        val validate = Button(this).apply { text = getString(ru.dioneya.commissioning.R.string.server_validate) }
        val scanProfile = Button(this).apply { text = getString(ru.dioneya.commissioning.R.string.server_scan_profile) }
        val saveProfile = Button(this).apply { text = getString(ru.dioneya.commissioning.R.string.server_save_profile) }
        root.addView(scanProfile); root.addView(saveProfile)
        root.addView(validate); root.addView(apply); root.addView(selfTest)
        root.addView(Button(this).apply {
            text = getString(ru.dioneya.commissioning.R.string.server_next_installation)
            setOnClickListener {
                startActivity(android.content.Intent(this@ServerActivity, InstallationActivity::class.java)
                    .putExtra(InstallationActivity.EXTRA_DEVICE_ADDRESS, intent.getStringExtra(EXTRA_DEVICE_ADDRESS))
                    .putExtra(InstallationActivity.EXTRA_STATION_SERIAL, intent.getStringExtra(EXTRA_STATION_SERIAL)))
            }
        })
        status = TextView(this).apply { textSize = 16f; setPadding(0, pad, 0, 0) }
        details = TextView(this).apply { textSize = 13f; setPadding(0, pad / 2, 0, 0) }
        root.addView(status); root.addView(details)
        setContentView(ScrollView(this).apply { addView(root) })

        val address = intent.getStringExtra(EXTRA_DEVICE_ADDRESS).orEmpty()
        val device = if (address.isNotEmpty() && BluetoothAdapter.checkBluetoothAddress(address)) bluetoothDevice(address) else null
        if (device == null) {
            apply.isEnabled = false; selfTest.isEnabled = false
            status.text = getString(ru.dioneya.commissioning.R.string.server_no_device)
        }
        val transport = device?.let { AndroidBleTransport(this, it) }
        val s = BleSession(transport ?: NoTransport)
        session = s
        controller = ServerScreenController(s) { st -> runOnUiThread { render(st) } }.also { c ->
            c.sessionConnectedProbe = { transport?.isConnected ?: false }
        }

        scanProfile.setOnClickListener { startActivityForResult(android.content.Intent(this, QrScanActivity::class.java), REQUEST_PROFILE_QR) }
        saveProfile.setOnClickListener {
            val p = ServerProfile.fromFields(readFields())
            if (p == null) status.text = getString(ru.dioneya.commissioning.R.string.server_profile_not_savable)
            else { profiles.save(p); status.text = getString(ru.dioneya.commissioning.R.string.server_profile_saved, p.host, p.mqttPort) }
        }
        if (saved != null) status.text = getString(ru.dioneya.commissioning.R.string.server_profile_loaded, saved.host, saved.mqttPort)
        validate.setOnClickListener { controller?.let { c -> c.edit(readFields()); c.buildPatch()?.let { status.text = getString(ru.dioneya.commissioning.R.string.server_valid) } } }
        apply.setOnClickListener { if (ensurePermission()) { controller?.edit(readFields()); executor.execute { controller?.apply() } } }
        selfTest.setOnClickListener { if (ensurePermission()) executor.execute { controller?.runSelfTest() } }
    }

    override fun onActivityResult(requestCode: Int, resultCode: Int, data: android.content.Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode != REQUEST_PROFILE_QR || resultCode != RESULT_OK) return
        val p = data?.getStringExtra(QrScanActivity.EXTRA_PROFILE_TEXT)?.let { ServerProfile.decode(it) } ?: return
        val current = readFields()
        val merged = p.copy(apn1 = current.apn1, apn2 = current.apn2, preferredSim = current.preferredSim)
        applyFields(merged.toFields(current))
        profiles.save(merged)
        status.text = getString(ru.dioneya.commissioning.R.string.server_profile_scanned, p.host, p.mqttPort)
    }

    private fun applyFields(f: ServerScreenController.Fields) {
        inputs.getValue("hostPort").setText(f.hostPort); inputs.getValue("httpsPort").setText(f.httpsPort)
        inputs.getValue("caReference").setText(f.caReference); inputs.getValue("fingerprintHex").setText(f.fingerprintHex)
        inputs.getValue("topicPrefix").setText(f.topicPrefix); inputs.getValue("apn1").setText(f.apn1); inputs.getValue("apn2").setText(f.apn2)
        simSlot = f.preferredSim
    }

    private fun readFields() = ServerScreenController.Fields(
        hostPort = inputs.getValue("hostPort").text.toString(), httpsPort = inputs.getValue("httpsPort").text.toString(),
        caReference = inputs.getValue("caReference").text.toString(), fingerprintHex = inputs.getValue("fingerprintHex").text.toString(),
        tenant = inputs.getValue("tenant").text.toString(), topicPrefix = inputs.getValue("topicPrefix").text.toString(),
        version = inputs.getValue("version").text.toString(), preferredSim = simSlot,
        apn1 = inputs.getValue("apn1").text.toString(), apn2 = inputs.getValue("apn2").text.toString(),
    )

    private fun render(st: ServerScreenController.State) {
        status.text = when (st.phase) {
            ServerScreenController.Phase.EDITING -> ""
            ServerScreenController.Phase.INVALID -> getString(ru.dioneya.commissioning.R.string.server_invalid, st.errors.joinToString(", "))
            ServerScreenController.Phase.CONNECTING -> getString(ru.dioneya.commissioning.R.string.server_connecting)
            ServerScreenController.Phase.WRITING -> getString(ru.dioneya.commissioning.R.string.server_writing)
            ServerScreenController.Phase.READING_BACK -> getString(ru.dioneya.commissioning.R.string.server_reading_back)
            ServerScreenController.Phase.VERIFIED -> getString(ru.dioneya.commissioning.R.string.server_verified, st.message)
            ServerScreenController.Phase.MISMATCH -> getString(ru.dioneya.commissioning.R.string.server_mismatch)
            ServerScreenController.Phase.REJECTED, ServerScreenController.Phase.ERROR -> st.message
            ServerScreenController.Phase.SELF_TEST -> getString(ru.dioneya.commissioning.R.string.server_self_test_running)
            ServerScreenController.Phase.SELF_TEST_DONE -> st.message
        }
        details.text = buildString {
            st.readback?.let { rb ->
                append("station_id ").append(rb.stationId).append("  host ").append(rb.endpoint.host).append(':').append(rb.endpoint.mqttPort)
                append("  tenant ").append(rb.endpoint.tenant).append("  v").append(rb.version).append('\n')
                append("hash ").append(st.stationHashHex).append('\n')
            }
            for (r in st.selfTest) append(r.name).append(": ").append(r.codeName).append(" (").append(r.detail).append(")\n")
        }
        details.visibility = if (details.text.isEmpty()) View.GONE else View.VISIBLE
    }

    private fun bluetoothDevice(address: String): BluetoothDevice? =
        (getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter?.getRemoteDevice(address)

    private fun ensurePermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true
        if (checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) == PackageManager.PERMISSION_GRANTED) return true
        requestPermissions(arrayOf(Manifest.permission.BLUETOOTH_CONNECT), REQUEST_BLUETOOTH)
        return false
    }

    override fun onDestroy() {
        super.onDestroy()
        executor.execute { session?.run({ session?.disconnect() }, 3000) }
        executor.shutdown()
        session?.close()
    }

    /** Transport used when no device address was given: every operation fails cleanly. */
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
        const val EXTRA_DEVICE_ADDRESS = "ru.dioneya.commissioning.DEVICE_ADDRESS"
        const val EXTRA_STATION_SERIAL = "ru.dioneya.commissioning.STATION_SERIAL"
        /** Tenant from the label QR, used as the default of the tenant field. */
        const val EXTRA_TENANT = "ru.dioneya.commissioning.TENANT"
        /** Label pairing secret (base32) for the pairing step of the joint prototype; held in the intent only, never persisted. */
        const val EXTRA_PAIRING_SECRET = "ru.dioneya.commissioning.PAIRING_SECRET"
        private const val REQUEST_BLUETOOTH = 41
        private const val REQUEST_PROFILE_QR = 46
    }
}
