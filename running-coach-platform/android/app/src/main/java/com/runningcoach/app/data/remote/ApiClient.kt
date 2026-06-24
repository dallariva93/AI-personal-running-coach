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

    @Synchronized
    fun service(baseUrl: String, token: String): ApiService {
        val key = "$baseUrl|$token"
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
            .baseUrl(baseUrl)
            .client(client)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)

        cachedKey = key
        cachedService = service
        return service
    }
}
