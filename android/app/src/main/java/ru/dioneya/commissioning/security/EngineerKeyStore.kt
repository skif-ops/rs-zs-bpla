package ru.dioneya.commissioning.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import ru.dioneya.commissioning.core.role.EngineerKey
import java.io.File
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Engineer keys (B.9) on the phone: one file per station serial, sealed with an AES-256-GCM
 * key that lives in the Android Keystore (non-exportable, generated on first use).  The
 * registry export is imported once (file picker), then only the sealed copy remains; nothing
 * of the key is logged, shown or shared.  The whole store can be wiped by the engineer.
 */
class EngineerKeyStore(context: Context) {
    private val dir = File(context.filesDir, "engineer-keys").apply { mkdirs() }

    fun has(serial: String): Boolean = fileFor(serial).exists()

    fun serials(): List<String> = dir.listFiles()?.filter { it.name.endsWith(EXT) }?.map { it.name.removeSuffix(EXT) }?.sorted().orEmpty()

    /** Parses the export text and seals the key under its own serial; null when the text is not a valid export. */
    fun importExport(text: String): EngineerKey? {
        val key = EngineerKey.fromExportJson(text) ?: return null
        put(key)
        return key
    }

    fun put(key: EngineerKey) {
        val cipher = Cipher.getInstance(TRANSFORM)
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey())
        cipher.updateAAD(key.serial.toByteArray(Charsets.US_ASCII))
        val sealed = cipher.doFinal(key.key)
        val iv = cipher.iv
        fileFor(key.serial).writeBytes(byteArrayOf(VERSION, iv.size.toByte()) + iv + sealed)
    }

    /** Null when absent or when the sealed copy cannot be opened (Keystore reset, tampering). */
    fun get(serial: String): EngineerKey? {
        val f = fileFor(serial)
        if (!f.exists()) return null
        return try {
            val blob = f.readBytes()
            if (blob.size < 2 || blob[0] != VERSION) return null
            val ivLen = blob[1].toInt() and 0xFF
            val iv = blob.copyOfRange(2, 2 + ivLen)
            val sealed = blob.copyOfRange(2 + ivLen, blob.size)
            val cipher = Cipher.getInstance(TRANSFORM)
            cipher.init(Cipher.DECRYPT_MODE, wrappingKey(), GCMParameterSpec(TAG_BITS, iv))
            cipher.updateAAD(serial.toByteArray(Charsets.US_ASCII))
            EngineerKey(serial, cipher.doFinal(sealed))
        } catch (_: Exception) {
            null
        }
    }

    fun forget(serial: String): Boolean = fileFor(serial).delete()

    fun forgetAll() { dir.listFiles()?.forEach { it.delete() } }

    private fun fileFor(serial: String): File {
        require(serial.matches(Regex("[A-Za-z0-9._-]{1,64}"))) { "unsafe serial" }
        return File(dir, serial + EXT)
    }

    private fun wrappingKey(): SecretKey {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        gen.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build())
        return gen.generateKey()
    }

    companion object {
        private const val ANDROID_KEYSTORE = "AndroidKeyStore"
        private const val ALIAS = "dioneya-engineer-key-wrap"
        private const val TRANSFORM = "AES/GCM/NoPadding"
        private const val TAG_BITS = 128
        private const val EXT = ".sealed"
        private const val VERSION: Byte = 1
    }
}
