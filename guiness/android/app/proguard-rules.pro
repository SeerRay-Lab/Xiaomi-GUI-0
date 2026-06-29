# Kotlinx Serialization
-keepattributes *Annotation*, InnerClasses
-dontnote kotlinx.serialization.AnnotationsKt
-keepclassmembers class kotlinx.serialization.json.** {
    *** Companion;
}
-keepclasseswithmembers class kotlinx.serialization.json.** {
    kotlinx.serialization.KSerializer serializer(...);
}
-keep,includedescriptorclasses class com.guiness.controller.**$$serializer { *; }
-keepclassmembers class com.guiness.controller.** {
    *** Companion;
}
-keepclasseswithmembers class com.guiness.controller.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# Ktor
-dontwarn io.ktor.**
-keep class io.ktor.** { *; }

# Netty (transitive via Ktor CIO should not trigger; guard anyway)
-dontwarn io.netty.**
-dontwarn org.slf4j.**

# 保留 AccessibilityService 和 ForegroundService 入口
-keep class com.guiness.controller.service.** { *; }
