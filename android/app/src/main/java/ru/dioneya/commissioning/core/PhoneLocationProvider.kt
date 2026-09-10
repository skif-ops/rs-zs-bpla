package ru.dioneya.commissioning.core

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.location.Location
import android.location.LocationListener
import android.location.LocationManager
import android.os.Build
import android.os.Bundle

class PhoneLocationProvider(private val context: Context) {
    private val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager

    fun hasFineLocationPermission(): Boolean =
        context.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED

    fun requestSingleLocation(onResult: (Location?) -> Unit) {
        if (!hasFineLocationPermission()) {
            onResult(null)
            return
        }

        val provider = when {
            manager.isProviderEnabled(LocationManager.GPS_PROVIDER) -> LocationManager.GPS_PROVIDER
            manager.isProviderEnabled(LocationManager.NETWORK_PROVIDER) -> LocationManager.NETWORK_PROVIDER
            else -> null
        }
        if (provider == null) {
            onResult(bestLastKnown())
            return
        }

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                manager.getCurrentLocation(provider, null, context.mainExecutor) { location ->
                    onResult(location ?: bestLastKnown())
                }
            } else {
                @Suppress("DEPRECATION")
                manager.requestSingleUpdate(
                    provider,
                    object : LocationListener {
                        override fun onLocationChanged(location: Location) = onResult(location)
                        override fun onProviderEnabled(provider: String) = Unit
                        override fun onProviderDisabled(provider: String) = Unit
                        @Deprecated("Deprecated in Android framework")
                        override fun onStatusChanged(provider: String?, status: Int, extras: Bundle?) = Unit
                    },
                    null,
                )
            }
        } catch (_: SecurityException) {
            onResult(null)
        } catch (_: IllegalArgumentException) {
            onResult(bestLastKnown())
        }
    }

    fun bestLastKnown(): Location? {
        if (!hasFineLocationPermission()) return null
        return try {
            listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
                .mapNotNull { provider -> runCatching { manager.getLastKnownLocation(provider) }.getOrNull() }
                .maxByOrNull { it.time }
        } catch (_: SecurityException) {
            null
        }
    }

    fun toInstallationPosition(location: Location, version: Long = 1): InstallationPosition {
        val accuracy = if (location.hasAccuracy()) location.accuracy.toInt().coerceAtLeast(1) else 50
        return InstallationPosition(
            latE7 = (location.latitude * 1e7).toInt(),
            lonE7 = (location.longitude * 1e7).toInt(),
            altDm = if (location.hasAltitude()) (location.altitude * 10.0).toInt() else 0,
            accuracyM = accuracy.coerceAtMost(1000),
            source = CoordinateSource.PHONE_LOCATION,
            version = version,
            locked = true,
        )
    }
}
