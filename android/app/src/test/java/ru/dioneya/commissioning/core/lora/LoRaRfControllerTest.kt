package ru.dioneya.commissioning.core.lora

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Test
import ru.dioneya.commissioning.core.ble.BleSession
import ru.dioneya.commissioning.core.ble.FakeBleTransport
import ru.dioneya.commissioning.core.ble.GattContractV01

class LoRaRfControllerTest {
    private fun status(mode: Int, remaining: Int): ByteArray = ByteArray(20).also {
        it[0] = 1; it[1] = 1; it[2] = mode.toByte(); it[3] = 9; it[4] = 14; it[6] = 1
        val frequency = 868_900_000L
        for (i in 0..3) it[8 + i] = (frequency ushr (8 * i)).toByte()
        for (i in 0..3) it[16 + i] = (remaining ushr (8 * i)).toByte()
    }

    @Test fun timedTestUsesOneCharacteristic() {
        val transport = FakeBleTransport()
        val session = BleSession(transport, 500)
        session.connect()
        transport.onWrite = { characteristic, _ ->
            if (characteristic == GattContractV01.CHAR_LORA_CONTROL) {
                transport.notify(characteristic, status(1, 300))
                transport.notify(characteristic, byteArrayOf(GattContractV01.WRITE_STATUS_OK.toByte()))
            }
        }
        assertEquals(300L, LoRaRfController(session).startTest(300).testRemainingSeconds)
        assertNotNull(transport.writtenValue(GattContractV01.CHAR_LORA_CONTROL))
        session.close()
    }

    @Test fun packageAcceptsRawHexAndJson() {
        val raw = ByteArray(96) { it.toByte() }
        val hex = raw.joinToString("") { "%02x".format(it.toInt() and 0xff) }
        assertEquals(raw.toList(), LoRaRfProfilePackage.parse(raw)?.toList())
        assertEquals(raw.toList(), LoRaRfProfilePackage.parse(hex.toByteArray())?.toList())
        assertEquals(raw.toList(), LoRaRfProfilePackage.parse("{\"profile_hex\":\"$hex\"}".toByteArray())?.toList())
    }
}
