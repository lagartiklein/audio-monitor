import org.jetbrains.kotlin.gradle.dsl.JvmTarget

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
    alias(libs.plugins.compose.compiler)
    id("com.google.gms.google-services")
    alias(libs.plugins.google.firebase.crashlytics)
    alias(libs.plugins.google.firebase.firebase.perf)
    id("kotlin-parcelize")
}

android {
    namespace = "com.cepalabsfree.fichatech"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.cepalabsfree.fichatech"
        minSdk = 29
        targetSdk = 36
        versionCode = 76
        versionName = "Gratis"

        ndk {
            debugSymbolLevel = "SYMBOL_TABLE"
            abiFilters += listOf("armeabi-v7a", "arm64-v8a", "x86_64")
        }

        externalNativeBuild {
            cmake {
                cppFlags += listOf(
                    "-std=c++17",
                    "-O3",
                    "-ffast-math",
                    "-DOBOE_ENABLE_LOGGING=1"
                )
                arguments += listOf(
                    "-DANDROID_STL=c++_shared",
                    "-DANDROID_PLATFORM=android-29"
                )
            }
        }

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    signingConfigs {
        // Configuración vacía, ya que firmas manualmente
        getByName("debug") {
            // Configuración por defecto para debug
        }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            isDebuggable = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("debug") // Cambia esto cuando firmes manualmente

            ndk {
                debugSymbolLevel = "SYMBOL_TABLE"
            }
        }

        debug {
            isDebuggable = true
            ndk {
                debugSymbolLevel = "FULL"
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        compose = true
        viewBinding = true
        dataBinding = true
        prefab = true
    }

    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.13"
    }

    // ========================================
    // 🔥 CRÍTICO: ALINEACIÓN 16KB EN ZIP
    // ========================================
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }

        jniLibs {
            useLegacyPackaging = false
        }
    }

    kotlin {
        compilerOptions {
            jvmTarget = JvmTarget.JVM_17
        }
    }

    // ✅ Configurar zipalign con 16KB
    applicationVariants.all {
        outputs.all {
            val output = this as? com.android.build.gradle.internal.api.BaseVariantOutputImpl
            output?.outputFileName = output?.outputFileName?.replace(
                "app-", "app-16kb-"
            )
        }
    }

    androidResources {
        noCompress += listOf("so")
    }
}

dependencies {
    // ✅ Oboe 1.9.1+ (con soporte 16KB)
    implementation("com.google.oboe:oboe:1.10.0")

    implementation("com.google.protobuf:protobuf-javalite:3.25.3")

    implementation(platform("com.google.firebase:firebase-bom:34.6.0"))
    implementation(libs.firebase.firestore.ktx)
    implementation(libs.firebase.crashlytics)
    implementation(libs.firebase.auth)
    implementation(libs.firebase.perf)
    implementation("com.google.firebase:firebase-analytics")

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    implementation(libs.androidx.drawerlayout)
    implementation(libs.material)
    implementation(libs.androidx.preference.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.activity)
    implementation(libs.androidx.constraintlayout)
    implementation(libs.androidx.recyclerview)
    implementation(libs.androidx.room.ktx)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.androidx.media3.common)

    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services.auth)
    implementation(libs.googleid)
    implementation("com.google.android.gms:play-services-auth:21.4.0")

    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    implementation(libs.material3)
    implementation("androidx.compose.material3:material3-window-size-class:1.4.0")
    implementation(libs.androidx.runtime.livedata)
    implementation(libs.androidx.material.icons.extended)

    implementation(libs.play.services.ads)
    implementation("com.google.android.ump:user-messaging-platform:2.1.0")

    implementation(libs.accompanist.permissions)
    implementation("androidx.swiperefreshlayout:swiperefreshlayout:1.1.0")

    implementation(libs.itextg)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)
}

configurations.all {
    resolutionStrategy {
        force("com.google.protobuf:protobuf-javalite:3.25.3")
        force("com.google.guava:guava:31.0.1-jre")
        force("org.hamcrest:hamcrest:2.2")
        force("junit:junit:4.13.2")
    }

    exclude(group = "org.bouncycastle", module = "bcprov-jdk15on")
    exclude(group = "org.bouncycastle", module = "bcpkix-jdk15on")
}

// ========================================
// 🔥 TAREA PERSONALIZADA PARA ZIPALIGN 16KB
// ========================================
abstract class Align16KBTask : DefaultTask() {
    @get:Inject
    abstract val execOps: ExecOperations

    @TaskAction
    fun applyZipalign() {
        println("✅ Aplicando zipalign 16KB a APKs...")

        val android = project.extensions.getByType(com.android.build.gradle.AppExtension::class.java)
        val buildDir = project.layout.buildDirectory.get().asFile
        val apkDir = File(buildDir, "outputs/apk")

        project.fileTree(apkDir).matching {
            include("**/*.apk")
            exclude("**/*-aligned.apk")
        }.forEach { apkFile ->
            val alignedFile = File(apkFile.parent, apkFile.name.replace(".apk", "-aligned.apk"))
            val zipalignPath = File(android.sdkDirectory, "build-tools/${android.buildToolsVersion}/zipalign")

            if (zipalignPath.exists()) {
                try {
                    execOps.exec {
                        commandLine(
                            zipalignPath.absolutePath,
                            "-p",  // Page-align native libraries
                            "-f",  // Force overwrite
                            "16",  // 16KB alignment
                            apkFile.absolutePath,
                            alignedFile.absolutePath
                        )
                    }

                    if (alignedFile.exists()) {
                        println("  ✅ ${apkFile.name} -> ${alignedFile.name}")

                        // Verificar alineación
                        try {
                            execOps.exec {
                                commandLine(
                                    zipalignPath.absolutePath,
                                    "-c", "-v", "16",
                                    alignedFile.absolutePath
                                )
                            }
                            println("  ✅ Verificación de alineación exitosa")
                        } catch (e: Exception) {
                            println("  ⚠️ No se pudo verificar la alineación: ${e.message}")
                        }
                    } else {
                        println("  ❌ Error: No se creó ${alignedFile.name}")
                    }
                } catch (e: Exception) {
                    println("  ❌ Error al ejecutar zipalign: ${e.message}")
                }
            } else {
                println("  ❌ zipalign no encontrado en: $zipalignPath")
                println("  ℹ️ Asegúrate de tener instalado el build-tools ${android.buildToolsVersion}")
            }
        }
    }
}

tasks.register<Align16KBTask>("align16KB")

// ========================================
// TASK PARA VERIFICAR 16KB
// ========================================
tasks.register("verify16KB") {
    doLast {
        println("🔍 Verificando alineación 16KB...")
        println("   Ejecuta manualmente:")
        println("   zipalign -c -v 16 app/build/outputs/apk/debug/app-debug-16kb-aligned.apk")
        println("   O usa Android Studio: Build > Analyze APK")
    }
}
