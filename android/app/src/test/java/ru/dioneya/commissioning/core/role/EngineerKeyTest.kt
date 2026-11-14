package ru.dioneya.commissioning.core.role

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class EngineerKeyTest {
    private val vectorKey = ByteArray(32) { (0xa0 + it).toByte() }
    private val vectorNonce = ByteArray(16) { it.toByte() }

    /** ICD v0.2 §4 / addendum B.9 vector, shared with firmware test_ble_bridge.c and PKI test_pki_engineer_key.py. */
    @Test fun roleTagMatchesTheIcdVector() {
        val tag = EngineerKey("DIO-EVT-012", vectorKey).roleTag(vectorNonce)
        assertEquals("e3f70cf47e0a591490b501d6ba31be7b", EngineerKey.bytesToHex(tag))
        assertEquals(16, tag.size)
        // the serial is part of the MAC input: another station's nonce gives another tag
        assertEquals(false, EngineerKey.bytesToHex(EngineerKey("DIO-EVT-013", vectorKey).roleTag(vectorNonce)) == "e3f70cf47e0a591490b501d6ba31be7b")
    }

    @Test fun parsesTheRegistryExport() {
        val text = """{
  "serial": "DIO-EVT-012",
  "engineer_key_hex": "${EngineerKey.bytesToHex(vectorKey)}",
  "context": "DIO-ROLE-V1"
}"""
        val k = EngineerKey.fromExportJson(text)!!
        assertEquals("DIO-EVT-012", k.serial)
        assertArrayEquals(vectorKey, k.key)
        // compact form and missing context are accepted; foreign context, short key or bad hex are not
        assertEquals("DIO-EVT-012", EngineerKey.fromExportJson("""{"serial":"DIO-EVT-012","engineer_key_hex":"${EngineerKey.bytesToHex(vectorKey)}"}""")!!.serial)
        assertNull(EngineerKey.fromExportJson("""{"serial":"DIO-EVT-012","engineer_key_hex":"${EngineerKey.bytesToHex(vectorKey)}","context":"OTHER"}"""))
        assertNull(EngineerKey.fromExportJson("""{"serial":"DIO-EVT-012","engineer_key_hex":"a0a1a2"}"""))
        assertNull(EngineerKey.fromExportJson("""{"serial":"DIO-EVT-012","engineer_key_hex":"${"zz".repeat(32)}"}"""))
        assertNull(EngineerKey.fromExportJson("""{"engineer_key_hex":"${EngineerKey.bytesToHex(vectorKey)}"}"""))
        assertNull(EngineerKey.fromExportJson("not json"))
    }

    @Test fun hexRoundTrip() {
        assertArrayEquals(byteArrayOf(0, 0x7f, -1), EngineerKey.hexToBytes("007fff"))
        assertArrayEquals(byteArrayOf(0x0a), EngineerKey.hexToBytes("0A"))
        assertNull(EngineerKey.hexToBytes("abc"))
        assertNull(EngineerKey.hexToBytes(""))
        assertEquals("007fff", EngineerKey.bytesToHex(byteArrayOf(0, 0x7f, -1)))
    }
}
