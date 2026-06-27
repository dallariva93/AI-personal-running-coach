package com.runningcoach.app.data.remote

import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

/**
 * Builds [ApiService] instances for a given base URL + token, caching the last
 * one so we only rebuild when the connection settings actually change.
 */
object ApiClient {

    private var cachedKey: String? = null
    private var cachedService: ApiService? = null

    /** Upgrade http:// → https:// unless the host is a local address. */
    private fun normalizeUrl(url: String): String {
        if (!url.startsWith("http://", ignoreCase = true)) return url
        val localHosts = listOf("localhost", "10.0.2.2", "127.0.0.1")
        val host = url.removePrefix("http://").removePrefix("HTTP://").substringBefore("/").substringBefore(":")
        return if (host in localHosts) url else url.replaceFirst("http://", "https://", ignoreCase = true)
    }

    @Synchronized
    fun service(baseUrl: String, token: String): ApiService {
        val normalizedUrl = normalizeUrl(baseUrl)
        val key = "$normalizedUrl|$token"
        cachedService?.let { if (key == cachedKey) return it }

        val logging = HttpLoggingInterceptor().apply {
            level = HttpLoggingInterceptor.Level.BASIC
        }

        val client = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS) // AI calls can take a while
            .addInterceptor { chain ->
                val builder = chain.request().newBuilder()
                if (token.isNotBlank()) {
                    builder.addHeader("Authorization", "Bearer $token")
                }
                chain.proceed(builder.build())
            }
            .addInterceptor(logging)
            .build()

        val service = Retrofit.Builder()
            .baseUrl(normalizedUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)

        cachedKey = key
        cachedService = service
        return service
    }
}
