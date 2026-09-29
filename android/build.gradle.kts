// Versions follow Thumb-Key (https://github.com/dessalines/thumb-key), which will embed the
// library: the same Android Gradle Plugin, Kotlin, compile SDK, minSdk 24 and JVM 17.
plugins {
    id("com.android.application") version "9.4.1" apply false
    id("com.android.library") version "9.4.1" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.4.20" apply false
    id("org.jmailen.kotlinter") version "5.7.0" apply false
}

subprojects {
    apply(plugin = "org.jmailen.kotlinter")
}
