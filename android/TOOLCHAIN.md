# Android toolchain baseline

Статус: `SOURCE BASELINE / RELEASE BUILD NOT AUTHORIZED`

| Компонент | Версия |
|---|---|
| Android Gradle Plugin | 9.4.0 |
| Gradle | 9.6.0 |
| JDK | 17 |
| compileSdk / targetSdk | 36 |
| minSdk | 28 (Android 9) |
| SDK Build Tools | 36.0.0 |

Основание:

- https://developer.android.com/build/releases/agp-9-4-0-release-notes
- https://developer.android.com/build/jdks

Проект использует built-in Kotlin Android Gradle Plugin. Версии проверяются CI. Release signing material в репозитории отсутствует.

API 37 указан AGP 9.4 как максимально поддерживаемый, но пакет `platforms;android-37` не был доступен через `sdkmanager` на CI при проверке baseline. Поэтому воспроизводимая сборка зафиксирована на доступном API 36 до отдельного контролируемого обновления.
