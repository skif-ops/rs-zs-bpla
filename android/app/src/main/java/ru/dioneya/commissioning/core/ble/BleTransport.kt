package ru.dioneya.commissioning.core.ble

import java.util.UUID

/** Any BLE failure surfaced to the session layer; [code] is a GATT status or one of the [BleError] values. */
class BleException(message: String, val code: Int = BleError.GENERIC) : Exception(message)

object BleError {
    const val GENERIC = -1
    const val TIMEOUT = -2
    const val DISCONNECTED = -3
    const val FRAMING = -4
    const val NOT_FOUND = -5
    const val CANCELLED = -6
    const val STATION_REJECTED = -7
}

/**
 * Blocking GATT primitives; implemented by the Android binding over BluetoothGatt
 * and by a fake in unit tests.  All calls are made from the single [BleSession]
 * worker thread, one at a time, so implementations need no internal queue.
 */
interface BleTransport {
    /** Connects and discovers services; returns the negotiated ATT MTU. */
    fun connect(timeoutMs: Long): Int
    fun disconnect()
    val isConnected: Boolean

    /** Writes one ATT packet with response. */
    fun write(characteristic: UUID, value: ByteArray, timeoutMs: Long)
    /** Reads one ATT packet. */
    fun read(characteristic: UUID, timeoutMs: Long): ByteArray
    /** Enables/disables notifications; notified values arrive through [NotificationSink]. */
    fun setNotifications(characteristic: UUID, enabled: Boolean, timeoutMs: Long)
    fun setNotificationSink(sink: NotificationSink?)

    fun interface NotificationSink {
        fun onNotification(characteristic: UUID, value: ByteArray)
    }
}
