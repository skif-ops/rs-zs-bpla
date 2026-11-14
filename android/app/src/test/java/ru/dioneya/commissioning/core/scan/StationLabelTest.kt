package ru.dioneya.commissioning.core.scan

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class StationLabelTest {
    /** Known answer shared with server/tests/test_pki_labels.py::test_label_payload_crc_and_roundtrip. */
    private val vector = "DIO1;S=DIO-EVT-012;ID=12;T=pilot1;K=JBSWY3DPEHPK3PXPJBSWY3DPEH;C=C5A3"

    @Test fun crcMatchesTheReferenceCheckValue() {
        assertEquals(0x29B1, StationLabel.crc16Ccitt("123456789".toByteArray()))
    }

    @Test fun decodesTheServerVectorAndReencodesIdentically() {
        val l = StationLabel.decode(vector)!!
        assertEquals(StationLabel("DIO-EVT-012", 12, "pilot1", "JBSWY3DPEHPK3PXPJBSWY3DPEH"), l)
        assertEquals(vector, l.encode())
        assertEquals(l, StationLabel.decode("  $vector\n"))
        assertArrayEquals("Hello!\u00de\u00ad\u00be\u00efHello!".toByteArray(Charsets.ISO_8859_1), l.pairingSecretBytes())   // 26 base32 chars = 16 bytes
        assertEquals(16, l.pairingSecretBytes().size)
        assertEquals("020559", l.pairingPasskey())                                   // shared with the nRF52840 bridge (SHA-256 e6f81f0f...)
        val bench = StationLabel("DIO-EVT-B01", 901, "bench", "JBSWY3DPEHPK3PXPJBSWY3DPEH")
        assertEquals(bench, StationLabel.decode(bench.encode()))
    }

    @Test fun rejectsCorruptedOrForeignLabels() {
        assertNull(StationLabel.decode(vector.dropLast(1) + "4"))                       // crc
        assertNull(StationLabel.decode(vector.replace("ID=12", "ID=13")))              // crc fails first; recomputed below
        val wrongId = StationLabel("DIO-EVT-012", 13, "pilot1", "JBSWY3DPEHPK3PXPJBSWY3DPEH").encode()
        assertNull(StationLabel.decode(wrongId))                                       // id does not match the serial
        assertNull(StationLabel.decode(StationLabel("DIO-EVT-041", 41, "pilot2", "JBSWY3DPEHPK3PXPJBSWY3DPEH").encode()))
        assertNull(StationLabel.decode(vector.replace("DIO1", "DIO2")))
        assertNull(StationLabel.decode(vector.replace(";C=", "")))
        assertNull(StationLabel.decode("https://example.com/not-a-label"))
        assertNull(StationLabel.decode(StationLabel("DIO-EVT-012", 12, "pilot 1", "JBSWY3DPEHPK3PXPJBSWY3DPEH").encode()))
    }
}
