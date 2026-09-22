package ru.dioneya.commissioning.ui

import android.Manifest
import android.app.Activity
import android.bluetooth.BluetoothManager
import android.bluetooth.le.BluetoothLeScanner
import android.bluetooth.le.ScanCallback
import android.bluetooth.le.ScanResult
import android.bluetooth.le.ScanSettings
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import ru.dioneya.commissioning.R
import ru.dioneya.commissioning.ble.AndroidBleTransport
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.scan.StationScanController
import java.util.concurrent.Executors

/**
 * Station picker: BLE scan for the Device Info service / `DIO-EVT-` names, optional
 * expected serial (typed from the label; QR lands with the camera step), tap a
 * station to read `identity`, then continue to [ServerActivity] with its address.
 * Scanning needs BLUETOOTH_SCAN + BLUETOOTH_CONNECT (API 31+) or location (API 28-30).
 */
class StationPickerActivity : Activity() {
    private val controller = StationScanController { st -> runOnUiThread { render(st) } }
    private val executor = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private var scanner: BluetoothLeScanner? = null
    private var scanning = false
    private var session: BleSession? = null
    private lateinit var list: LinearLayout
    private lateinit var status: TextView
    private lateinit var continueButton: Button
    private lateinit var serialInput: EditText

    private val scanCallback = object : ScanCallback() {
        override fun onScanResult(callbackType: Int, result: ScanResult) {
            val record = result.scanRecord
            val uuids = record?.serviceUuids?.map { it.uuid } ?: emptyList()
            val name = record?.deviceName ?: safeName(result)
            controller.onAdvertisement(StationScanController.Advertisement(result.device.address, name, uuids, result.rssi), System.currentTimeMillis())
        }
        override fun onScanFailed(errorCode: Int) { runOnUiThread { status.text = getString(R.string.picker_scan_failed, errorCode) } }
    }

    private val expireTick = object : Runnable {
        override fun run() { controller.expire(System.currentTimeMillis()); handler.postDelayed(this, 3000) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val pad = (16 * resources.displayMetrics.density).toInt()
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(pad, pad, pad, pad) }
        root.addView(TextView(this).apply { text = getString(R.string.picker_title); textSize = 22f })
        serialInput = EditText(this).apply { hint = getString(R.string.picker_expected_serial); inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_CHARACTERS }
        serialInput.setOnFocusChangeListener { _, focused -> if (!focused && !controller.setExpectedSerial(serialInput.text.toString())) status.text = getString(R.string.picker_bad_serial) }
        root.addView(serialInput)
        status = TextView(this).apply { textSize = 15f; setPadding(0, pad / 2, 0, pad / 2) }
        root.addView(status)
        list = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        root.addView(list)
        continueButton = Button(this).apply { text = getString(R.string.picker_continue); isEnabled = false }
        continueButton.setOnClickListener {
            val sel = controller.state.selected ?: return@setOnClickListener
            startActivity(Intent(this, ServerActivity::class.java).putExtra(ServerActivity.EXTRA_DEVICE_ADDRESS, sel.address)
                .putExtra(ServerActivity.EXTRA_STATION_SERIAL, controller.state.identity?.serial))
        }
        root.addView(continueButton)
        root.addView(Button(this).apply { text = getString(R.string.picker_rescan); setOnClickListener { controller.resume(); startScan() } })
        setContentView(ScrollView(this).apply { addView(root) })
    }

    override fun onResume() { super.onResume(); startScan(); handler.post(expireTick) }
    override fun onPause() { super.onPause(); stopScan(); handler.removeCallbacks(expireTick) }
    override fun onDestroy() { super.onDestroy(); session?.let { s -> executor.execute { try { s.run({ s.disconnect() }, 3000) } catch (_: Exception) {} }; s.close() }; executor.shutdown() }

    private fun render(st: StationScanController.State) {
        list.removeAllViews()
        for (c in st.candidates) {
            list.addView(Button(this).apply {
                text = getString(R.string.picker_candidate, c.name ?: getString(R.string.picker_unnamed), c.address, c.rssi)
                isEnabled = st.phase == StationScanController.Phase.SCANNING
                setOnClickListener { if (ensurePermissions()) { stopScan(); confirm(c) } }
            })
        }
        status.text = when (st.phase) {
            StationScanController.Phase.SCANNING -> if (st.candidates.isEmpty()) getString(R.string.picker_scanning) else getString(R.string.picker_found, st.candidates.size)
            StationScanController.Phase.CONFIRMING -> getString(R.string.picker_confirming, st.selected?.address ?: "")
            StationScanController.Phase.CONFIRMED -> getString(R.string.picker_confirmed, st.message)
            StationScanController.Phase.MISMATCH, StationScanController.Phase.ERROR -> st.message
        }
        continueButton.isEnabled = st.phase == StationScanController.Phase.CONFIRMED
    }

    private fun confirm(c: StationScanController.Candidate) {
        val device = (getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter?.getRemoteDevice(c.address) ?: return
        session?.close()
        val s = BleSession(AndroidBleTransport(this, device))
        session = s
        executor.execute { controller.confirm(c, s); try { s.run({ s.disconnect() }, 3000) } catch (_: Exception) {} }
    }

    private fun startScan() {
        if (scanning || !ensurePermissions()) return
        val adapter = (getSystemService(Context.BLUETOOTH_SERVICE) as? BluetoothManager)?.adapter
        if (adapter == null || !adapter.isEnabled) { status.text = getString(R.string.picker_bluetooth_off); return }
        scanner = adapter.bluetoothLeScanner ?: return
        /* No ScanFilter: the nRF advertisement layout (service UUID vs. local name) is settled with the prototype;
           the controller filters on both, and unfiltered scans stop on onPause so the radio is not held. */
        val settings = ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build()
        scanner?.startScan(null, settings, scanCallback)
        scanning = true
    }

    private fun stopScan() {
        if (!scanning) return
        try { scanner?.stopScan(scanCallback) } catch (_: Exception) {}
        scanning = false
    }

    private fun safeName(result: ScanResult): String? = try { result.device.name } catch (_: SecurityException) { null }

    private fun ensurePermissions(): Boolean {
        val needed = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) arrayOf(Manifest.permission.BLUETOOTH_SCAN, Manifest.permission.BLUETOOTH_CONNECT)
                     else arrayOf(Manifest.permission.ACCESS_FINE_LOCATION)
        val missing = needed.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) return true
        requestPermissions(missing.toTypedArray(), REQUEST_PERMISSIONS)
        return false
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_PERMISSIONS && grantResults.all { it == PackageManager.PERMISSION_GRANTED }) startScan()
        else status.text = getString(R.string.picker_permission_denied)
    }

    companion object { private const val REQUEST_PERMISSIONS = 42 }
}
