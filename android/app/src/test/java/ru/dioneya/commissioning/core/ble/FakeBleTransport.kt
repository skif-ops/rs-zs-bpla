package ru.dioneya.commissioning.core.ble

import java.util.UUID
import java.util.concurrent.CopyOnWriteArrayList

/** In-memory GATT peripheral for unit tests: framed values per characteristic, scripted notifications. */
class FakeBleTransport(var mtu: Int = GattContractV01.MTU_REQUEST) : BleTransport {
    private var sink: BleTransport.NotificationSink? = null
    override var isConnected: Boolean = false
        private set
    val writes = CopyOnWriteArrayList<Pair<UUID, ByteArray>>()
    val subscriptions = mutableMapOf<UUID, Boolean>()
    /** Values served by read(): a queue of frames per characteristic. */
    val readFrames = mutableMapOf<UUID, ArrayDeque<ByteArray>>()
    /** Handler invoked after every write; may notify through [notify]. */
    var onWrite: ((UUID, ByteArray) -> Unit)? = null
    var connectFails = false
    var readFails = false
    var connectCount = 0

    fun serveLong(characteristic: UUID, value: ByteArray, attPayload: Int = mtu - 3) {
        readFrames[characteristic] = ArrayDeque(LongValueFraming.split(value, attPayload))
    }

    fun notify(characteristic: UUID, value: ByteArray, attPayload: Int = mtu - 3) {
        for (frame in LongValueFraming.split(value, attPayload)) sink?.onNotification(characteristic, frame)
    }

    fun notifyRaw(characteristic: UUID, frame: ByteArray) { sink?.onNotification(characteristic, frame) }

    /** Reassembles the frames written to [characteristic] into the logical value. */
    fun writtenValue(characteristic: UUID): ByteArray? {
        val r = LongValueFraming.Reassembler()
        for ((c, f) in writes) if (c == characteristic) { if (!r.feed(f)) return null; if (r.complete) return r.value }
        return null
    }

    override fun connect(timeoutMs: Long): Int {
        connectCount++
        if (connectFails) throw BleException("connect failed", BleError.DISCONNECTED)
        isConnected = true
        return mtu
    }
    override fun disconnect() { isConnected = false }
    override fun write(characteristic: UUID, value: ByteArray, timeoutMs: Long) {
        if (!isConnected) throw BleException("not connected", BleError.DISCONNECTED)
        writes.add(characteristic to value.copyOf())
        onWrite?.invoke(characteristic, value)
    }
    override fun read(characteristic: UUID, timeoutMs: Long): ByteArray {
        if (!isConnected) throw BleException("not connected", BleError.DISCONNECTED)
        if (readFails) throw BleException("read failed 0x85", 0x85)
        return readFrames[characteristic]?.removeFirstOrNull() ?: throw BleException("nothing to read", BleError.NOT_FOUND)
    }
    override fun setNotifications(characteristic: UUID, enabled: Boolean, timeoutMs: Long) { subscriptions[characteristic] = enabled }
    override fun setNotificationSink(sink: BleTransport.NotificationSink?) { this.sink = sink }
}
