package ru.dioneya.commissioning.core.ble

import java.util.UUID
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.Future
import java.util.concurrent.TimeUnit

/**
 * Serialised BLE operations on top of [BleTransport]: one worker thread, one
 * operation at a time, each with its own timeout.  Long values are framed with
 * [LongValueFraming] (ATT payload = MTU - 3).  Notification-driven requests
 * (config_write status, self-test report) subscribe, write, then wait for the
 * complete framed value on the same or a paired characteristic.
 */
class BleSession(private val transport: BleTransport, private val opTimeoutMs: Long = GattContractV01.TIMEOUT_OPERATION_MS) : AutoCloseable {
    private val worker: ExecutorService = Executors.newSingleThreadExecutor { r -> Thread(r, "ble-session").apply { isDaemon = true } }
    @Volatile var attPayload: Int = GattContractV01.MTU_MIN - 3
        private set
    @Volatile private var pending: Pending? = null

    private class Pending(val characteristic: UUID) {
        var reassembler = LongValueFraming.Reassembler()
        /** Every complete framed value notified while pending, in order (a request may answer with several). */
        val done = ArrayBlockingQueue<Result<ByteArray>>(8)
    }

    init {
        transport.setNotificationSink { characteristic, value ->
            val p = pending ?: return@setNotificationSink
            if (characteristic != p.characteristic) return@setNotificationSink
            if (!p.reassembler.feed(value)) {
                p.done.offer(Result.failure(BleException("framing error on $characteristic", BleError.FRAMING)))
            } else if (p.reassembler.complete) {
                p.done.offer(Result.success(p.reassembler.value))
                p.reassembler = LongValueFraming.Reassembler()
            }
        }
    }

    /** Submits [op] to the worker; the returned future completes with the result or a [BleException]. */
    fun <T> submit(op: () -> T): Future<T> = worker.submit(op)

    /** Runs [op] on the worker and waits for it; exceptions are rethrown as [BleException]. */
    fun <T> run(op: () -> T, timeoutMs: Long = opTimeoutMs * 4): T = try {
        submit(op).get(timeoutMs, TimeUnit.MILLISECONDS)
    } catch (e: java.util.concurrent.ExecutionException) {
        throw (e.cause as? BleException) ?: BleException(e.cause?.message ?: "operation failed")
    } catch (e: java.util.concurrent.TimeoutException) {
        throw BleException("operation timed out", BleError.TIMEOUT)
    }

    // ---- operations (worker thread) ---------------------------------------------------------

    fun connect(timeoutMs: Long = GattContractV01.TIMEOUT_CONNECT_MS) {
        val mtu = transport.connect(timeoutMs)
        attPayload = maxOf(GattContractV01.MTU_MIN, minOf(mtu, GattContractV01.MTU_REQUEST)) - 3
    }

    fun disconnect() = transport.disconnect()

    fun readShort(characteristic: UUID): ByteArray = transport.read(characteristic, opTimeoutMs)

    /** Reads a framed long value: repeated reads until the LAST frame. */
    fun readLong(characteristic: UUID): ByteArray {
        val r = LongValueFraming.Reassembler()
        var frames = 0
        while (!r.complete) {
            val frame = transport.read(characteristic, opTimeoutMs)
            if (!r.feed(frame)) throw BleException("framing error reading $characteristic", BleError.FRAMING)
            if (++frames > 64) throw BleException("value too long", BleError.FRAMING)
        }
        return r.value
    }

    /** Writes a framed long value, one ATT write with response per frame. */
    fun writeLong(characteristic: UUID, value: ByteArray) {
        for (frame in LongValueFraming.split(value, attPayload)) transport.write(characteristic, frame, opTimeoutMs)
    }

    /**
     * Writes [payload] (framed) to [writeChar] and waits for the complete framed
     * response notified on [notifyChar].  Subscribes for the duration of the request.
     */
    fun request(writeChar: UUID, notifyChar: UUID, payload: ByteArray, responseTimeoutMs: Long): ByteArray =
        requestSequence(writeChar, notifyChar, payload, responseTimeoutMs) { true }.first()

    /**
     * Like [request] but collects every complete framed value notified on [notifyChar] until
     * [last] accepts one; the timeout covers the whole sequence.  session_role (B.9) answers
     * a write with a value (`01‖nonce16` or `03‖role`) followed by the one-byte status.
     */
    fun requestSequence(writeChar: UUID, notifyChar: UUID, payload: ByteArray, responseTimeoutMs: Long,
                        last: (ByteArray) -> Boolean): List<ByteArray> {
        val p = Pending(notifyChar)
        pending = p
        try {
            transport.setNotifications(notifyChar, true, opTimeoutMs)
            writeLong(writeChar, payload)
            val values = ArrayList<ByteArray>()
            val deadline = System.nanoTime() + responseTimeoutMs * 1_000_000L
            while (true) {
                val left = (deadline - System.nanoTime()) / 1_000_000L
                val result = (if (left > 0) p.done.poll(left, TimeUnit.MILLISECONDS) else null)
                    ?: throw BleException("no response from $notifyChar", BleError.TIMEOUT)
                val v = result.getOrThrow()
                values.add(v)
                if (last(v)) return values
            }
        } finally {
            pending = null
            try { transport.setNotifications(notifyChar, false, opTimeoutMs) } catch (_: BleException) {}
        }
    }

    override fun close() {
        worker.shutdownNow()
    }
}
