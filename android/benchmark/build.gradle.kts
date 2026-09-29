import org.jetbrains.kotlin.gradle.dsl.JvmTarget

// Benchmark app for the Pixel 8 (M11): the pure-Kotlin engine against ONNX Runtime on the same
// drawings. ONNX Runtime is used here only, to answer the brief's question; the library and
// the demo never depend on it (DECISIONS.md, D36).

/** Copies the ONNX reference and the parity fixtures (the benchmark's drawings) from export/. */
abstract class CopyBenchmarkAssets : DefaultTask() {
    @get:InputFiles
    abstract val sources: ConfigurableFileCollection

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        val output = outputDir.get().asFile
        output.deleteRecursively()
        output.mkdirs()
        sources.forEach { it.copyTo(output.resolve(it.name)) }
    }
}

plugins {
    id("com.android.application")
}

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.fromTarget("17")
    }
}

android {
    namespace = "io.github.toldry.glyphsketch.benchmark"
    compileSdk = 37

    defaultConfig {
        applicationId = "io.github.toldry.glyphsketch.benchmark"
        minSdk = 24
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
    }

    buildTypes {
        release {
            // Timings come from an optimized build; the debug key is enough for adb installs.
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = signingConfigs.getByName("debug")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

val exportDir = rootProject.file("../export")
val copyBenchmarkAssets =
    tasks.register<CopyBenchmarkAssets>("copyBenchmarkAssets") {
        sources.from(listOf("glyphsketch.onnx", "fixtures.json").map { exportDir.resolve(it) })
        outputDir.set(layout.buildDirectory.dir("generated/benchmarkAssets"))
    }

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(
            copyBenchmarkAssets,
            CopyBenchmarkAssets::outputDir,
        )
    }
}

dependencies {
    implementation(project(":glyphsketch"))
    implementation("com.microsoft.onnxruntime:onnxruntime-android:1.30.0")
}
