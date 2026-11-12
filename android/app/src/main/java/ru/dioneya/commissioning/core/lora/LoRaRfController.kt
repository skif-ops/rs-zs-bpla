package ru.dioneya.commissioning.core.lora

import ru.dioneya.commissioning.core.ble.BleException
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.GattContractV01

data class LoRaRfStatus(
    val radioReady: Boolean,
    val mode: Int,
    val spreadingFactor: Int,
    val txDbm: Int,
    val profileId: Int,
    val frequencyHz: Long,
    val profileVersion: Long,
    val testRemainingSeconds: Long,
) {
    val modeName: String get() = when (mode) { 1 -> "RF-тест"; 2 -> "полевой"; else -> "передача выключена" }

    companion object {
        fun decode(value: ByteArray): LoRaRfStatus? {
            if (value.size != 20 || value[0].toInt() != 1) return null
            fun u16(offset: Int) = (value[offset].toInt() and 0xff) or ((value[offset + 1].toInt() and 0xff) shl 8)
            fun u32(offset: Int): Long = (0 until 4).fold(0L) { acc, i -> acc or ((value[offset + i].toLong() and 0xff) shl (8 * i)) }
            return LoRaRfStatus(value[1].toInt() != 0, value[2].toInt() and 0xff, value[3].toInt() and 0xff,
                value[4].toInt(), u16(6), u32(8), u32(12), u32(16))
        }
    }
}

object LoRaRfProfilePackage {
    fun parse(data: ByteArray): ByteArray? {
        if (data.size == GattContractV01.LORA_PROFILE_BYTES) return data.copyOf()
        val text = data.toString(Charsets.UTF_8).trim()
        val hex = if (text.length == GattContractV01.LORA_PROFILE_BYTES * 2) text
            else Regex("\"profile_hex\"\\s*:\\s*\"([0-9a-fA-F]{192})\"").find(text)?.groupValues?.get(1)
        if (hex == null || !hex.matches(Regex("[0-9a-fA-F]{192}"))) return null
        return ByteArray(GattContractV01.LORA_PROFILE_BYTES) { i -> hex.substring(i * 2, i * 2 + 2).toInt(16).toByte() }
    }
}

class LoRaRfController(private val session: BleSession) {
    fun readStatus(): LoRaRfStatus = LoRaRfStatus.decode(session.readLong(GattContractV01.CHAR_LORA_CONTROL))
        ?: throw BleException("invalid LoRa status")

    fun startTest(seconds: Int): LoRaRfStatus {
        require(seconds in 1..900)
        return request(byteArrayOf(GattContractV01.LORA_OP_TEST, (seconds and 0xff).toByte(), (seconds ushr 8).toByte()))
    }

    fun stopTest(): LoRaRfStatus = request(byteArrayOf(GattContractV01.LORA_OP_STOP))

    fun installSignedProfile(record: ByteArray): LoRaRfStatus {
        require(record.size == GattContractV01.LORA_PROFILE_BYTES)
        return request(byteArrayOf(GattContractV01.LORA_OP_INSTALL_PROFILE) + record)
    }

    private fun request(payload: ByteArray): LoRaRfStatus {
        val values = session.requestSequence(GattContractV01.CHAR_LORA_CONTROL, GattContractV01.CHAR_LORA_CONTROL,
            payload, GattContractV01.TIMEOUT_CONFIG_WRITE_MS) { it.size == 1 }
        val code = values.last().firstOrNull()?.toInt()?.and(0xff) ?: -1
        if (code != GattContractV01.WRITE_STATUS_OK) throw BleException("LoRa operation rejected, status $code")
        return values.dropLast(1).mapNotNull { LoRaRfStatus.decode(it) }.lastOrNull()
            ?: throw BleException("LoRa status was not returned")
    }
}
