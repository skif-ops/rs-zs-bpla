package ru.dioneya.commissioning.ble

import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothGatt
import android.bluetooth.BluetoothGattCallback
import android.bluetooth.BluetoothGattCharacteristic
import android.bluetooth.BluetoothGattDescriptor
import android.bluetooth.BluetoothProfile
import android.content.Context
import android.os.Build
import ru.dioneya.commissioning.core.ble.BleError
import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01
import java.util.UUID
import java.util.concurrent.SynchronousQueue
import java.util.concurrent.TimeUnit

/**
 * [BleTransport] over Android BluetoothGatt.  Every call blocks the BleSession
 * worker until the matching GATT callback arrives (or the timeout expires), so
 * the callback-driven Android API becomes the sequential API the session needs.
 * Requires BLUETOOTH_CONNECT (API 31+) granted by the Activity before use.
 */
class AndroidBleTransport(private val context: Context, private val device: BluetoothDevice) : BleTransport {
    private var gatt: BluetoothGatt? = null
    private val events = SynchronousQueue<Event>()
    @Volatile private var sink: BleTransport.NotificationSink? = null
    @Volatile override var isConnected: Boolean = false
        private set

    private sealed class Event {
        data class Connected(val status: Int, val state: Int) : Event()
        data class Services(val status: Int) : Event()
        data class Mtu(val mtu: Int, val status: Int) : Event()
        data class Read(val uuid: UUID, val value: ByteArray, val status: Int) : Event()
        data class Written(val uuid: UUID, val status: Int) : Event()
        data class DescriptorWritten(val uuid: UUID, val status: Int) : Event()
    }

    private val callback = object : BluetoothGattCallback() {
        override fun onConnectionStateChange(g: BluetoothGatt, status: Int, newState: Int) {
            isConnected = newState == BluetoothProfile.STATE_CONNECTED && status == BluetoothGatt.GATT_SUCCESS
            events.offer(Event.Connected(status, newState), 1, TimeUnit.SECONDS)
        }
        override fun onServicesDiscovered(g: BluetoothGatt, status: Int) { events.offer(Event.Services(status), 1, TimeUnit.SECONDS) }
        override fun onMtuChanged(g: BluetoothGatt, mtu: Int, status: Int) { events.offer(Event.Mtu(mtu, status), 1, TimeUnit.SECONDS) }
        @Suppress("DEPRECATION")
        override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            if (Build.VERSION.SDK_INT < 33) events.offer(Event.Read(c.uuid, c.value ?: ByteArray(0), status), 1, TimeUnit.SECONDS)
        }
        override fun onCharacteristicRead(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray, status: Int) {
            events.offer(Event.Read(c.uuid, value, status), 1, TimeUnit.SECONDS)
        }
        override fun onCharacteristicWrite(g: BluetoothGatt, c: BluetoothGattCharacteristic, status: Int) {
            events.offer(Event.Written(c.uuid, status), 1, TimeUnit.SECONDS)
        }
        override fun onDescriptorWrite(g: BluetoothGatt, d: BluetoothGattDescriptor, status: Int) {
            events.offer(Event.DescriptorWritten(d.characteristic.uuid, status), 1, TimeUnit.SECONDS)
        }
        @Suppress("DEPRECATION")
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic) {
            if (Build.VERSION.SDK_INT < 33) sink?.onNotification(c.uuid, c.value ?: ByteArray(0))
        }
        override fun onCharacteristicChanged(g: BluetoothGatt, c: BluetoothGattCharacteristic, value: ByteArray) {
            sink?.onNotification(c.uuid, value)
        }
    }

    private inline fun <reified T : Event> await(timeoutMs: Long, what: String): T {
        val deadline = System.currentTimeMillis() + timeoutMs
        while (true) {
            val remaining = deadline - System.currentTimeMillis()
            if (remaining <= 0) throw BleException("$what timed out", BleError.TIMEOUT)
            val e = events.poll(remaining, TimeUnit.MILLISECONDS) ?: throw BleException("$what timed out", BleError.TIMEOUT)
            if (e is Event.Connected && e.state != BluetoothProfile.STATE_CONNECTED) {
                isConnected = false
                throw BleException("disconnected during $what (status ${e.status})", BleError.DISCONNECTED)
            }
            if (e is T) return e
        }
    }

    private fun characteristic(uuid: UUID): BluetoothGattCharacteristic {
        val g = gatt ?: throw BleException("not connected", BleError.DISCONNECTED)
        for (service in g.services) service.getCharacteristic(uuid)?.let { return it }
        throw BleException(uuid.toString(), BleError.NOT_FOUND)
    }

    override fun connect(timeoutMs: Long): Int {
        disconnect()
        val g = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) device.connectGatt(context, false, callback, BluetoothDevice.TRANSPORT_LE)
                else device.connectGatt(context, false, callback)
        gatt = g ?: throw BleException("connectGatt returned null")
        val c = await<Event.Connected>(timeoutMs, "connect")
        if (c.status != BluetoothGatt.GATT_SUCCESS) throw BleException("connect status ${c.status}", c.status)
        var mtu = GattContractV01.MTU_MIN
        if (g.requestMtu(GattContractV01.MTU_REQUEST)) {
            val m = await<Event.Mtu>(timeoutMs, "mtu")
            if (m.status == BluetoothGatt.GATT_SUCCESS) mtu = m.mtu
        }
        if (!g.discoverServices()) throw BleException("discoverServices refused")
        val s = await<Event.Services>(timeoutMs, "service discovery")
        if (s.status != BluetoothGatt.GATT_SUCCESS) throw BleException("service discovery status ${s.status}", s.status)
        return mtu
    }

    override fun disconnect() {
        gatt?.let { it.disconnect(); it.close() }
        gatt = null
        isConnected = false
    }

    @Suppress("DEPRECATION")
    override fun write(characteristic: UUID, value: ByteArray, timeoutMs: Long) {
        val g = gatt ?: throw BleException("not connected", BleError.DISCONNECTED)
        val c = characteristic(characteristic)
        val ok = if (Build.VERSION.SDK_INT >= 33) {
            g.writeCharacteristic(c, value, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == BluetoothGatt.GATT_SUCCESS
        } else {
            c.writeType = BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT
            c.value = value
            g.writeCharacteristic(c)
        }
        if (!ok) throw BleException("write refused")
        val w = await<Event.Written>(timeoutMs, "write")
        if (w.status != BluetoothGatt.GATT_SUCCESS) throw BleException("write status ${w.status}", w.status)
    }

    override fun read(characteristic: UUID, timeoutMs: Long): ByteArray {
        val g = gatt ?: throw BleException("not connected", BleError.DISCONNECTED)
        if (!g.readCharacteristic(characteristic(characteristic))) throw BleException("read refused")
        val r = await<Event.Read>(timeoutMs, "read")
        if (r.status != BluetoothGatt.GATT_SUCCESS) throw BleException("read status ${r.status}", r.status)
        return r.value
    }

    @Suppress("DEPRECATION")
    override fun setNotifications(characteristic: UUID, enabled: Boolean, timeoutMs: Long) {
        val g = gatt ?: throw BleException("not connected", BleError.DISCONNECTED)
        val c = characteristic(characteristic)
        if (!g.setCharacteristicNotification(c, enabled)) throw BleException("notification setup refused")
        val d = c.getDescriptor(GattContractV01.CCCD) ?: throw BleException("CCCD missing on $characteristic", BleError.NOT_FOUND)
        val v = if (enabled) BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE else BluetoothGattDescriptor.DISABLE_NOTIFICATION_VALUE
        val ok = if (Build.VERSION.SDK_INT >= 33) g.writeDescriptor(d, v) == BluetoothGatt.GATT_SUCCESS
                 else { d.value = v; g.writeDescriptor(d) }
        if (!ok) throw BleException("descriptor write refused")
        val w = await<Event.DescriptorWritten>(timeoutMs, "descriptor write")
        if (w.status != BluetoothGatt.GATT_SUCCESS) throw BleException("descriptor status ${w.status}", w.status)
    }

    override fun setNotificationSink(sink: BleTransport.NotificationSink?) { this.sink = sink }
}
