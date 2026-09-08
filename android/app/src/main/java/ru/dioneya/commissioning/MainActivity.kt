package ru.dioneya.commissioning

import android.app.Activity
import android.os.Bundle
import android.view.Gravity
import android.widget.LinearLayout
import android.widget.TextView

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
        setContentView(layout)
    }
}
