package ru.dioneya.commissioning

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import ru.dioneya.commissioning.ui.ServerActivity
import ru.dioneya.commissioning.ui.StationPickerActivity

class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val padding = (24 * resources.displayMetrics.density).toInt()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(padding, padding, padding, padding)
        }
        layout.addView(TextView(this).apply {
            text = getString(R.string.baseline_title)
            textSize = 24f
        })
        layout.addView(TextView(this).apply {
            text = getString(R.string.baseline_status)
            textSize = 16f
            setPadding(0, padding, 0, 0)
        })
        layout.addView(Button(this).apply {
            text = getString(R.string.open_station_picker)
            setOnClickListener { startActivity(Intent(this@MainActivity, StationPickerActivity::class.java)) }
        })
        layout.addView(Button(this).apply {
            text = getString(R.string.open_server_screen)
            setOnClickListener { startActivity(Intent(this@MainActivity, ServerActivity::class.java)) }
        })
        setContentView(layout)
    }
}
