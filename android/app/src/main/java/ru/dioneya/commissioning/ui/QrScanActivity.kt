package ru.dioneya.commissioning.ui

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.media.ImageReader
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.view.Surface
import android.view.TextureView
import android.widget.FrameLayout
import android.widget.TextView
import com.google.zxing.BarcodeFormat
import com.google.zxing.BinaryBitmap
import com.google.zxing.DecodeHintType
import com.google.zxing.MultiFormatReader
import com.google.zxing.NotFoundException
import com.google.zxing.PlanarYUVLuminanceSource
import com.google.zxing.common.HybridBinarizer
import ru.dioneya.commissioning.R
import ru.dioneya.commissioning.core.profile.ServerProfile
import ru.dioneya.commissioning.core.scan.StationLabel

/**
 * Scans a Dioneya QR with camera2 + ZXing core (no Play Services): a station label
 * (returned in [EXTRA_LABEL_TEXT]) or a server profile (returned in [EXTRA_PROFILE_TEXT]).
 * Other QR codes are ignored and the preview keeps running.
 */
class QrScanActivity : Activity() {
    private lateinit var preview: TextureView
    private lateinit var hint: TextView
    private var camera: CameraDevice? = null
    private var session: CameraCaptureSession? = null
    private var reader: ImageReader? = null
    private var thread: HandlerThread? = null
    private var handler: Handler? = null
    @Volatile private var done = false
    private val decoder = MultiFormatReader().apply {
        setHints(mapOf(DecodeHintType.POSSIBLE_FORMATS to listOf(BarcodeFormat.QR_CODE), DecodeHintType.TRY_HARDER to true))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val root = FrameLayout(this)
        preview = TextureView(this)
        hint = TextView(this).apply { text = getString(R.string.qr_hint); textSize = 16f; setPadding(24, 24, 24, 24) }
        root.addView(preview); root.addView(hint)
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.CAMERA), REQUEST_CAMERA)
            return
        }
        if (preview.isAvailable) openCamera() else preview.surfaceTextureListener = object : TextureView.SurfaceTextureListener {
            override fun onSurfaceTextureAvailable(s: SurfaceTexture, w: Int, h: Int) = openCamera()
            override fun onSurfaceTextureSizeChanged(s: SurfaceTexture, w: Int, h: Int) {}
            override fun onSurfaceTextureDestroyed(s: SurfaceTexture): Boolean = true
            override fun onSurfaceTextureUpdated(s: SurfaceTexture) {}
        }
    }

    override fun onPause() { closeCamera(); super.onPause() }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQUEST_CAMERA && grantResults.firstOrNull() != PackageManager.PERMISSION_GRANTED) {
            hint.text = getString(R.string.qr_no_permission)
        }
    }

    private fun openCamera() {
        val manager = getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val id = manager.cameraIdList.firstOrNull { manager.getCameraCharacteristics(it).get(CameraCharacteristics.LENS_FACING) == CameraCharacteristics.LENS_FACING_BACK }
            ?: manager.cameraIdList.firstOrNull() ?: run { hint.text = getString(R.string.qr_no_camera); return }
        thread = HandlerThread("qr-camera").also { it.start(); handler = Handler(it.looper) }
        reader = ImageReader.newInstance(WIDTH, HEIGHT, ImageFormat.YUV_420_888, 2).also { r ->
            r.setOnImageAvailableListener({ ir ->
                val image = ir.acquireLatestImage() ?: return@setOnImageAvailableListener
                try { if (!done) decode(image.planes[0].buffer.let { b -> ByteArray(b.remaining()).also { b.get(it) } }, image.planes[0].rowStride, image.height) }
                finally { image.close() }
            }, handler)
        }
        try {
            manager.openCamera(id, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) { camera = device; startPreview(device) }
                override fun onDisconnected(device: CameraDevice) { device.close(); camera = null }
                override fun onError(device: CameraDevice, error: Int) { device.close(); camera = null; runOnUiThread { hint.text = getString(R.string.qr_camera_error, error) } }
            }, handler)
        } catch (e: SecurityException) {
            hint.text = getString(R.string.qr_no_permission)
        }
    }

    @Suppress("DEPRECATION")
    private fun startPreview(device: CameraDevice) {
        val texture = preview.surfaceTexture ?: return
        texture.setDefaultBufferSize(WIDTH, HEIGHT)
        val previewSurface = Surface(texture)
        val readerSurface = reader?.surface ?: return
        val request = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW).apply {
            addTarget(previewSurface); addTarget(readerSurface)
            set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
        }
        device.createCaptureSession(listOf(previewSurface, readerSurface), object : CameraCaptureSession.StateCallback() {
            override fun onConfigured(s: CameraCaptureSession) { session = s; try { s.setRepeatingRequest(request.build(), null, handler) } catch (_: Exception) {} }
            override fun onConfigureFailed(s: CameraCaptureSession) { runOnUiThread { hint.text = getString(R.string.qr_camera_error, -1) } }
        }, handler)
    }

    /** Luma plane only (Y of YUV_420_888) is enough for ZXing. */
    private fun decode(luma: ByteArray, rowStride: Int, height: Int) {
        val source = PlanarYUVLuminanceSource(luma, rowStride, height, 0, 0, rowStride, height, false)
        val text = try { decoder.decodeWithState(BinaryBitmap(HybridBinarizer(source))).text } catch (_: NotFoundException) { null } finally { decoder.reset() }
        val result = Intent()
        when {
            text == null -> return
            StationLabel.decode(text) != null -> result.putExtra(EXTRA_LABEL_TEXT, StationLabel.decode(text)!!.encode())
            ServerProfile.decode(text) != null -> result.putExtra(EXTRA_PROFILE_TEXT, ServerProfile.decode(text)!!.encode())
            else -> return
        }
        done = true
        runOnUiThread { setResult(RESULT_OK, result); finish() }
    }

    private fun closeCamera() {
        try { session?.close() } catch (_: Exception) {}
        session = null
        camera?.close(); camera = null
        reader?.close(); reader = null
        thread?.quitSafely(); thread = null; handler = null
    }

    companion object {
        const val EXTRA_LABEL_TEXT = "ru.dioneya.commissioning.LABEL_TEXT"
        const val EXTRA_PROFILE_TEXT = "ru.dioneya.commissioning.PROFILE_TEXT"
        private const val REQUEST_CAMERA = 43
        private const val WIDTH = 1280
        private const val HEIGHT = 720
    }
}
