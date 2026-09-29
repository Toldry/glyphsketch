import org.jetbrains.kotlin.gradle.dsl.JvmTarget

/** Copies files from outside android/ into a generated source directory, under `into`. */
abstract class CopyIntoSources : DefaultTask() {
    @get:InputFiles
    abstract val sources: ConfigurableFileCollection

    @get:Input
    abstract val into: Property<String>

    @get:OutputDirectory
    abstract val outputDir: DirectoryProperty

    @TaskAction
    fun copy() {
        val output = outputDir.get().asFile
        output.deleteRecursively()
        val target = output.resolve(into.get()).apply { mkdirs() }
        sources.forEach { it.copyTo(target.resolve(it.name)) }
    }
}

plugins {
    id("com.android.library")
    id("com.vanniktech.maven.publish")
}

kotlin {
    // Every public declaration says so: the published API is deliberate. (A recorded API
    // dump would catch accidental changes too, but neither the binary-compatibility-validator
    // nor Kotlin's abiValidation sees an AGP 9 library's classes yet.)
    explicitApi()
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
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
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
// The shipped files from export/ become the library's assets.
val copyExportAssets =
    tasks.register<CopyIntoSources>("copyExportAssets") {
        into.set("")
        sources.from(
            listOf("glyphsketch-model.bin", "glyphsketch-index.bin", "glyphsketch-charset.json")
                .map { exportDir.resolve(it) },
        )
        outputDir.set(layout.buildDirectory.dir("generated/exportAssets"))
    }

// The license and the attribution notices travel inside the published library.
val copyNotices =
    tasks.register<CopyIntoSources>("copyNotices") {
        into.set("META-INF/glyphsketch")
        sources.from(rootProject.file("../LICENSE"), file("NOTICE.md"))
        outputDir.set(layout.buildDirectory.dir("generated/notices"))
    }

androidComponents {
    onVariants { variant ->
        variant.sources.assets?.addGeneratedSourceDirectory(
            copyExportAssets,
            CopyIntoSources::outputDir,
        )
        variant.sources.resources?.addGeneratedSourceDirectory(
            copyNotices,
            CopyIntoSources::outputDir,
        )
    }
}

// No runtime dependencies: the engine is plain Kotlin, so F-Droid builds it from source
// with nothing native (DECISIONS.md, D36).
dependencies {
    testImplementation("junit:junit:4.13.2")
    // On a device or emulator: ./gradlew :glyphsketch:connectedDebugAndroidTest
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
}

mavenPublishing {
    coordinates("io.github.toldry", "glyphsketch", providers.gradleProperty("VERSION_NAME").get())
    publishToMavenCentral()
    // Signing needs the release key, which only the release workflow has; local
    // publishToMavenLocal runs unsigned.
    if (providers.gradleProperty("signingInMemoryKey").isPresent) signAllPublications()
    pom {
        name.set("glyphsketch")
        description.set(
            "Offline recognizer for hand-drawn Unicode characters: retrieval over font-glyph " +
                "embeddings, pure Kotlin, with the model included.",
        )
        inceptionYear.set("2026")
        url.set("https://github.com/Toldry/glyphsketch")
        licenses {
            license {
                name.set("GNU Affero General Public License v3.0 only")
                url.set("https://www.gnu.org/licenses/agpl-3.0.txt")
                distribution.set("repo")
            }
        }
        developers {
            developer {
                id.set("Toldry")
                name.set("Toldry")
                url.set("https://github.com/Toldry")
            }
        }
        scm {
            url.set("https://github.com/Toldry/glyphsketch")
            connection.set("scm:git:https://github.com/Toldry/glyphsketch.git")
            developerConnection.set("scm:git:ssh://git@github.com/Toldry/glyphsketch.git")
        }
    }
}
