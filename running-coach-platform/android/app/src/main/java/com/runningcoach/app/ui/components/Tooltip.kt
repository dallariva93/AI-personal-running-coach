package com.runningcoach.app.ui.components

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.runningcoach.app.ui.theme.BrandGreen

/** Content shown in the long-press tooltip dialog. */
data class MetricInfo(
    val title: String,
    val description: String,
    val optimalRange: String? = null,
)

/** Pre-defined tooltip content for all non-trivial training metrics. */
object MetricTooltips {

    val tsb = MetricInfo(
        title = "Forma · TSB (Training Stress Balance)",
        description = "Differenza tra fitness cronica (CTL) e fatica acuta (ATL). " +
            "Un valore positivo indica freschezza — stai recuperando più di quanto stai caricando. " +
            "Un valore negativo indica che la fatica supera la fitness costruita.",
        optimalRange = "Ideale: da −10 a +5.\n" +
            "Sopra +10 → detraining (stai facendo troppo poco).\n" +
            "Sotto −30 → sovrallenamento.",
    )

    val ctl = MetricInfo(
        title = "Fitness · CTL (Chronic Training Load)",
        description = "Media esponenziale del carico delle ultime ~6 settimane (τ = 42 giorni). " +
            "Rappresenta la base aerobica costruita nel tempo con allenamenti costanti. " +
            "Cresce lentamente: servono settimane per vederla salire.",
        optimalRange = "Non c'è un limite massimo: cresce col volume.\n" +
            "Runner amatoriale: 30–60 · Avanzato: 60–100 · Elite: 100+.",
    )

    val atl = MetricInfo(
        title = "Fatica · ATL (Acute Training Load)",
        description = "Media esponenziale del carico degli ultimi ~7 giorni (τ = 7 giorni). " +
            "Misura la stanchezza accumulata di recente. " +
            "Sale rapidamente dopo sessioni intense e scende altrettanto velocemente col riposo.",
        optimalRange = "ATL / CTL < 1.3 → carico gestibile.\n" +
            "ATL / CTL > 1.5 → sovraccarico acuto: attenzione agli infortuni.",
    )

    val acwr = MetricInfo(
        title = "ACWR · Rapporto di Carico Acuto/Cronico",
        description = "Rapporto tra il carico acuto (ATL, ultima settimana) e quello cronico (CTL, ultime ~4 settimane). " +
            "Misura quanto stai aumentando il carico rispetto alla tua base di fitness. " +
            "È uno dei migliori predittori di rischio infortuni.",
        optimalRange = "0.8 – 1.3 → zona sicura (verde).\n" +
            "> 1.5 → zona rossa: rischio infortuni fino a 5× superiore.\n" +
            "< 0.8 → detraining: stai facendo meno del dovuto.",
    )

    val hrv = MetricInfo(
        title = "HRV · RMSSD (Variabilità Cardiaca)",
        description = "Root Mean Square of Successive Differences: misura la variabilità tra battiti consecutivi. " +
            "Un HRV alto indica che il sistema nervoso autonomo è riposato e pronto allo stress. " +
            "Varia da persona a persona: confronta sempre col tuo valore baseline personale.",
        optimalRange = "Riferimento generale:\n" +
            "> 55 ms → ottimo recupero.\n" +
            "25 – 55 ms → normale.\n" +
            "< 25 ms → recupero insufficiente.",
    )

    val vo2max = MetricInfo(
        title = "VO₂max · Consumo Massimale di Ossigeno",
        description = "Quantità massima di ossigeno che i muscoli riescono a utilizzare per kg di peso corporeo. " +
            "È il principale indicatore di fitness aerobica. " +
            "Migliora principalmente con intervalli ad alta intensità e progressivi veloci nel lungo periodo.",
        optimalRange = "Uomini: < 40 basso · 40–50 medio · 50–60 buono · > 60 eccellente.\n" +
            "Donne: valori tipicamente ~10% inferiori.",
    )

    val readiness = MetricInfo(
        title = "Prontezza · Readiness Score",
        description = "Punteggio 0–100 che combina HRV, qualità del sonno, fatica soggettiva, " +
            "dolori muscolari e motivazione. Indica quanto sei pronto per un allenamento intenso oggi.",
        optimalRange = "≥ 80 → sessione intensa ok.\n" +
            "60 – 79 → allenamento moderato consigliato.\n" +
            "< 60 → recupero attivo o giorno di riposo.",
    )

    val injuryRisk = MetricInfo(
        title = "Rischio Infortuni",
        description = "Punteggio composito basato su ACWR, monotonia del carico e fatica accumulata. " +
            "Stima la probabilità di infortuni da sovraccarico. " +
            "Aumenta con incrementi troppo rapidi di volume o intensità settimana su settimana.",
        optimalRange = "Low → tutto ok.\n" +
            "Moderate → procedi con cautela, non aumentare il volume.\n" +
            "High → riduci del 15–20% questa settimana.\n" +
            "Critical → stop e recupero immediato.",
    )

    val intensityDistribution = MetricInfo(
        title = "Distribuzione Intensità · 80/20",
        description = "Quanto del tuo allenamento avviene a bassa intensità (facile) vs alta intensità (duro). " +
            "La ricerca mostra che i runner d'élite fanno ~80% del volume a intensità facile, " +
            "lasciando il 20% per sessioni di qualità. Troppo medio-duro porta a stagnazione.",
        optimalRange = "Obiettivo: ~80% facile · ~10% medio · ~10% duro.\n" +
            "Se la parte 'dura' supera il 20% sei in 'junk miles' — troppo intenso per recuperare, troppo lento per adattarsi.",
    )
}

/** AlertDialog shown on long press of a metric value. */
@Composable
fun MetricInfoDialog(info: MetricInfo, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = {
            Text(info.title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.Bold)
        },
        text = {
            Column {
                Text(info.description, style = MaterialTheme.typography.bodyMedium)
                info.optimalRange?.let { range ->
                    Spacer(Modifier.height(12.dp))
                    Text(
                        "Range ottimale",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = BrandGreen,
                    )
                    Spacer(Modifier.height(4.dp))
                    Text(
                        range,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(start = 8.dp),
                    )
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("OK") }
        },
    )
}
