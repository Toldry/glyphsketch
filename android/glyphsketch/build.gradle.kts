import org.jetbrains.kotlin.gradle.dsl.JvmTarget

/** Copies the shipped files from export/ into the library's assets (not kept in android/). */
abstract class CopyExportAssets : DefaultTask() {
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
    id("com.android.library")
}

kotlin {
    compilerOptions {
        jvmTarget = JvmTarget.fromTarget("17")
    }
}

android {
    namespace = "io.github.toldry.glyphsketch"
    compileSdk = 37

    defaultConfig {
        minSdk = 24
        consumerProguardFiles("consumer-rules.pro")
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    testOptions {
        unitTests.all {
            // The parity fixtures and the shipped files: ../../export in the repository.
            it.systemProperty("glyphsketch.exportDir", rootProject.file("../export").absolutePath)
            it.maxHeapSize = "2g"
        }
    }
}

val exportDir = rootProject.file("../export")
val copyExportAssets =
    tasks.register<CopyExportAssets>("copyExportAssets") {
        sources.from(
            listOf("glyphsketch-model.bin", "glyphsketch-index.bin", "glyphsketch-charset.json")
                .map { exportDir.resolve(it) },
        )
        outputDir.set(layout.buildDirectory.dir("generated/exportAssets"))
    }

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(
            copyExportAssets,
            CopyExportAssets::outputDir,
        )
    }
}

// No runtime dependencies: the engine is plain Kotlin, so F-Droid builds it from source
// with nothing native (DECISIONS.md, D36).
dependencies {
    testImplementation("junit:junit:4.13.2")
}
