package com.budget.app

import android.appwidget.AppWidgetManager
import android.content.ComponentName
import android.content.Intent
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject

/**
 * Activité principale — initialise Chaquopy, synchronise les données Bunq
 * et met à jour l'affichage + le widget.
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        // Démarrage de l'interpréteur Python (une seule fois par processus)
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }

        rafraichirDashboard()
    }

    /**
     * Récupère les données Python et met à jour l'interface.
     * Doit être appelé sur le thread principal (pas de réseau ici, seulement SQLite).
     */
    private fun rafraichirDashboard() {
        try {
            val dashboard = chargerDashboard()
            afficherDonnees(dashboard)
            demanderMiseAJourWidget()
        } catch (e: Exception) {
            afficherErreur(e.message ?: "Erreur inconnue")
        }
    }

    /**
     * Appelle Python pour obtenir le dict de données du dashboard.
     * La synchronisation Bunq est déclenchée séparément (voir synchroniserEnArrierePlan).
     */
    private fun chargerDashboard(): JSONObject {
        val py = Python.getInstance()
        val cheminDB = getDatabasePath("budget.db").absolutePath

        // Appel direct du module budget_logic sans synchronisation réseau
        val pyDashboard = py.getModule("budget_logic")
            .callAttr("get_dashboard_json_from_path", cheminDB)

        return JSONObject(pyDashboard.toString())
    }

    private fun afficherDonnees(dashboard: JSONObject) {
        val aujourd_hui = dashboard.getJSONObject("aujourd_hui")
        val mois = dashboard.getJSONObject("mois_courant")
        val solde = dashboard.getJSONObject("solde_budget")

        findViewById<TextView>(R.id.tvDepensesJour)?.text =
            "%.2f€".format(aujourd_hui.getDouble("total_depenses"))

        findViewById<TextView>(R.id.tvObjectif)?.text =
            "/ %.0f€".format(aujourd_hui.getDouble("objectif"))

        findViewById<TextView>(R.id.tvDepensesMois)?.text =
            "%.0f€ ce mois".format(mois.getDouble("total_depenses"))

        val soldeMontant = solde.getDouble("montant")
        val tvSolde = findViewById<TextView>(R.id.tvSolde)
        tvSolde?.text = if (soldeMontant >= 0)
            "+%.2f€".format(soldeMontant)
        else
            "%.2f€".format(soldeMontant)

        tvSolde?.setTextColor(
            if (solde.getBoolean("est_positif")) getColor(R.color.vert_budget)
            else getColor(R.color.rouge_budget)
        )
    }

    private fun afficherErreur(message: String) {
        findViewById<TextView>(R.id.tvStatut)?.text = "Erreur : $message"
    }

    /**
     * Envoie un broadcast pour forcer la mise à jour de toutes les instances du widget.
     */
    private fun demanderMiseAJourWidget() {
        val ids = AppWidgetManager.getInstance(this)
            .getAppWidgetIds(ComponentName(this, BudgetWidget::class.java))
        if (ids.isNotEmpty()) {
            val intent = Intent(AppWidgetManager.ACTION_APPWIDGET_UPDATE).apply {
                putExtra(AppWidgetManager.EXTRA_APPWIDGET_IDS, ids)
            }
            sendBroadcast(intent)
        }
    }
}
