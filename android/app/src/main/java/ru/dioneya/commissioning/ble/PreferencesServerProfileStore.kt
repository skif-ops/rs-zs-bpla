package ru.dioneya.commissioning.ble

import android.content.Context
import ru.dioneya.commissioning.core.profile.ServerProfile
import ru.dioneya.commissioning.core.profile.ServerProfileStore

/**
 * Server profile in app-private SharedPreferences (public pinning data only: host, ports,
 * CA reference, fingerprint, prefix, APNs). Stored in the checksummed text form, so a
 * corrupted entry loads as "no profile" instead of half-filled fields.
 */
class PreferencesServerProfileStore(context: Context) : ServerProfileStore {
    private val prefs = context.getSharedPreferences(FILE, Context.MODE_PRIVATE)
    override fun load(): ServerProfile? = prefs.getString(KEY, null)?.let { ServerProfileStore.Text.parse(it) }
    override fun save(profile: ServerProfile) { prefs.edit().putString(KEY, ServerProfileStore.Text.serialize(profile)).apply() }
    override fun clear() { prefs.edit().remove(KEY).apply() }

    private companion object {
        const val FILE = "server_profile"
        const val KEY = "active"
    }
}
