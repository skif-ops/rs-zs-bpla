package ru.dioneya.commissioning.core.ble

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger

class BleSessionTest {
    private val cfgWrite = GattContractV01.CHAR_CONFIG_WRITE
    private val cfgRead = GattContractV01.CHAR_CONFIG_READ

    @Test fun connectNegotiatesAttPayloadAndLongReadWrite() {
        val t = FakeBleTransport(mtu = 247)
        BleSession(t, opTimeoutMs = 500).use { s ->
            s.run({ s.connect() })
            assertEquals(244, s.attPayload)
            val value = ByteArray(700) { (it xor 0x5a).toByte() }
            t.serveLong(cfgRead, value)
            assertArrayEquals(value, s.run({ s.readLong(cfgRead) }))
            s.run({ s.writeLong(cfgWrite, value) })
            assertArrayEquals(value, t.writtenValue(cfgWrite))
            assertEquals(3, t.writes.size)
        }
        val small = FakeBleTransport(mtu = 23)
        BleSession(small, opTimeoutMs = 500).use { s ->
            s.run({ s.connect() })
            assertEquals(20, s.attPayload)
            s.run({ s.writeLong(cfgWrite, ByteArray(100)) })
            assertEquals(6, small.writes.size)                   // 16 + 5*18 = 106 >= 100
        }
    }

    @Test fun operationsAreSerialisedOnOneThread() {
        val t = FakeBleTransport()
        val running = AtomicInteger(); val maxConcurrent = AtomicInteger()
        val threads = mutableSetOf<String>()
        BleSession(t).use { s ->
            s.run({ s.connect() })
            val futures = (1..8).map { i ->
                s.submit {
                    val n = running.incrementAndGet(); maxConcurrent.updateAndGet { maxOf(it, n) }
                    synchronized(threads) { threads.add(Thread.currentThread().name) }
                    Thread.sleep(5); s.writeLong(cfgWrite, byteArrayOf(i.toByte())); running.decrementAndGet(); i
                }
            }
            assertEquals((1..8).toList(), futures.map { it.get(2, TimeUnit.SECONDS) })
        }
        assertEquals(1, maxConcurrent.get())
        assertEquals(setOf("ble-session"), threads)
        assertEquals((1..8).map { it.toByte() }, t.writes.map { it.second.last() })
    }

    @Test fun requestWaitsForFramedNotificationAndUnsubscribes() {
        val t = FakeBleTransport(mtu = 247)
        val report = ByteArray(500) { it.toByte() }
        t.onWrite = { c, _ -> if (c == cfgWrite) Thread { Thread.sleep(20); t.notify(cfgWrite, report) }.start() }
        BleSession(t, opTimeoutMs = 500).use { s ->
            s.run({ s.connect() })
            val got = s.run({ s.request(cfgWrite, cfgWrite, byteArrayOf(1, 2, 3), 1000) })
            assertArrayEquals(report, got)
            assertEquals(false, t.subscriptions[cfgWrite])
        }
    }

    @Test fun requestTimesOutAndFramingErrorsSurface() {
        val t = FakeBleTransport()
        BleSession(t, opTimeoutMs = 200).use { s ->
            s.run({ s.connect() })
            try { s.run({ s.request(cfgWrite, cfgWrite, byteArrayOf(1), 150) }); fail("expected timeout") }
            catch (e: BleException) { assertEquals(BleError.TIMEOUT, e.code) }
            t.onWrite = { _, _ -> t.notifyRaw(cfgWrite, byteArrayOf(7, 0, 1)) }   // seq 7 without FIRST
            try { s.run({ s.request(cfgWrite, cfgWrite, byteArrayOf(1), 500) }); fail("expected framing error") }
            catch (e: BleException) { assertEquals(BleError.FRAMING, e.code) }
            t.readFrames[cfgRead] = ArrayDeque(listOf(byteArrayOf(3, 2)))
            try { s.run({ s.readLong(cfgRead) }); fail("expected framing error") }
            catch (e: BleException) { assertEquals(BleError.FRAMING, e.code) }
        }
    }

    @Test fun transportFailuresPropagateAsBleExceptions() {
        val t = FakeBleTransport(); t.connectFails = true
        BleSession(t).use { s ->
            try { s.run({ s.connect() }); fail("expected disconnected") }
            catch (e: BleException) { assertEquals(BleError.DISCONNECTED, e.code) }
            t.connectFails = false; s.run({ s.connect() }); t.readFails = true
            try { s.run({ s.readLong(cfgRead) }); fail("expected gatt error") }
            catch (e: BleException) { assertEquals(0x85, e.code) }
        }
        val latch = CountDownLatch(1)
        val s2 = BleSession(FakeBleTransport())
        s2.submit { latch.countDown() }
        assertTrue(latch.await(1, TimeUnit.SECONDS))
        s2.close()
    }
}
