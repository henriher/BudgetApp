package com.budget.app

import android.app.PendingIntent
import android.appwidget.AppWidgetManager
import android.appwidget.AppWidgetProvider
import android.content.Context
import android.content.Intent
import android.widget.RemoteViews
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.*

/**
 * Widget écran d'accueil — mini tableau de bord budget.
 * Taille cible : 3 colonnes × 4 lignes (~220×294dp).
 * Layout et visuels détaillés à définir dans widget_budget.xml.
 */
class BudgetWidget : AppWidgetProvider() {

    override fun onUpdate(
        context: Context,
        appWidgetManager: AppWidgetManager,
        appWidgetIds: IntArray
    ) {
        for (widgetId in appWidgetIds) {
            mettreAJour(context, appWidgetManager, widgetId)
        }
    }

    private fun mettreAJour(
        context: Context,
        appWidgetManager: AppWidgetManager,
        widgetId: Int
    ) {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }

        val vues = RemoteViews(context.packageName, R.layout.widget_budget)

        try {
            val dashboard = chargerDashboard(context)
            remplirVues(vues, dashboard, context)
        } catch (e: Exception) {
            // Affichage minimal en cas d'erreur Python / SQLite
            vues.setTextViewText(R.id.widgetDepensesJour, "--€")
            vues.setTextViewText(R.id.widgetObjectif, "/ ${context.getString(R.string.widget_objectif_defaut)}")
            vues.setTextViewText(R.id.widgetMiseAJour, "Erreur")
        }

        // Tap sur le widget → ouvre MainActivity
        val pendingIntent = PendingIntent.getActivity(
            context, 0,
            Intent(context, MainActivity::class.java),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        vues.setOnClickPendingIntent(R.id.widgetConteneur, pendingIntent)

        appWidgetManager.updateAppWidget(widgetId, vues)
    }

    private fun chargerDashboard(context: Context): JSONObject {
        val py = Python.getInstance()
        val cheminDB = context.getDatabasePath("budget.db").absolutePath
        val jsonStr = py.getModule("budget_logic")
            .callAttr("get_dashboard_json_from_path", cheminDB)
            .toString()
        return JSONObject(jsonStr)
    }

    private fun remplirVues(vues: RemoteViews, dashboard: JSONObject, context: Context) {
        val aujourd_hui = dashboard.getJSONObject("aujourd_hui")
        val mois = dashboard.getJSONObject("mois_courant")
        val solde = dashboard.getJSONObject("solde_budget")

        val totalJour = aujourd_hui.getDouble("total_depenses")
        val objectif = aujourd_hui.getDouble("objectif")
        val statut = aujourd_hui.getString("statut")
        val soldeMontant = solde.getDouble("montant")

        // Dépenses du jour
        vues.setTextViewText(R.id.widgetDepensesJour, "%.2f€".format(totalJour))
        vues.setTextViewText(R.id.widgetObjectif, "/ %.0f€".format(objectif))

        // Couleur selon le statut budgétaire
        val couleur = when (statut) {
            "excellent", "ok" -> context.getColor(R.color.vert_budget)
            "attention"       -> context.getColor(R.color.orange_budget)
            else              -> context.getColor(R.color.rouge_budget)
        }
        vues.setTextColor(R.id.widgetDepensesJour, couleur)

        // Dépenses du mois (total / objectif)
        vues.setTextViewText(
            R.id.widgetDepensesMois,
            "%.0f€ / %.0f€".format(
                mois.getDouble("total_depenses"),
                mois.getDouble("objectif")
            )
        )

        // Solde budget cumulé
        val texteSolde = if (soldeMontant >= 0)
            "+%.2f€".format(soldeMontant)
        else
            "%.2f€".format(soldeMontant)
        vues.setTextViewText(R.id.widgetSolde, texteSolde)
        vues.setTextColor(
            R.id.widgetSolde,
            if (solde.getBoolean("est_positif")) context.getColor(R.color.vert_budget)
            else context.getColor(R.color.rouge_budget)
        )

        // Heure de dernière mise à jour
        val heureMaj = SimpleDateFormat("HH:mm", Locale.FRANCE).format(Date())
        vues.setTextViewText(R.id.widgetMiseAJour, "Màj $heureMaj")
    }

    override fun onEnabled(context: Context) {
        // Premier widget ajouté à l'écran d'accueil
    }

    override fun onDisabled(context: Context) {
        // Dernier widget retiré — libérer des ressources si nécessaire
    }
}
