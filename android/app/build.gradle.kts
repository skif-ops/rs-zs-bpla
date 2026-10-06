plugins {
    id("com.android.application")
}

val releaseKeystorePath = providers.environmentVariable("DIONEA_ANDROID_KEYSTORE").orNull
val releaseStorePassword = providers.environmentVariable("DIONEA_ANDROID_STORE_PASSWORD").orNull
val releaseKeyAlias = providers.environmentVariable("DIONEA_ANDROID_KEY_ALIAS").orNull
val releaseKeyPassword = providers.environmentVariable("DIONEA_ANDROID_KEY_PASSWORD").orNull
val releaseSigningReady = listOf(
    releaseKeystorePath,
    releaseStorePassword,
    releaseKeyAlias,
    releaseKeyPassword,
).all { !it.isNullOrBlank() }

val signedReleaseTasks = setOf("assembleRelease", "bundleRelease", "packageRelease")
if (gradle.startParameter.taskNames.any { it.substringAfterLast(':') in signedReleaseTasks } && !releaseSigningReady) {
    throw GradleException(
        "Release signing is required. Set DIONEA_ANDROID_KEYSTORE, " +
            "DIONEA_ANDROID_STORE_PASSWORD, DIONEA_ANDROID_KEY_ALIAS and DIONEA_ANDROID_KEY_PASSWORD."
    )
}

android {
    namespace = "ru.dioneya.commissioning"
    compileSdk = 36

    defaultConfig {
        applicationId = "ru.dioneya.commissioning"
        minSdk = 28
        targetSdk = 36
        versionCode = providers.environmentVariable("DIONEA_ANDROID_VERSION_CODE").orElse("2026100501").get().toInt()
        versionName = providers.environmentVariable("DIONEA_ANDROID_VERSION_NAME").orElse("0.1.0-bench.20261005").get()
    }

    signingConfigs {
        create("releaseConfigured") {
            if (releaseSigningReady) {
                storeFile = file(releaseKeystorePath!!)
                storePassword = releaseStorePassword
                keyAlias = releaseKeyAlias
                keyPassword = releaseKeyPassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            if (releaseSigningReady) {
                signingConfig = signingConfigs.getByName("releaseConfigured")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            it.useJUnit()
        }
    }
}

dependencies {
    implementation("com.google.zxing:core:3.5.3")   // QR decoding without Play Services (pure Java)
    testImplementation("junit:junit:4.13.2")
}
