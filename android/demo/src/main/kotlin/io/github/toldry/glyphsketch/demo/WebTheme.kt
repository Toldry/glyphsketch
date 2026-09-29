package io.github.toldry.glyphsketch.demo

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.LocalTextStyle
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** The web demo's colours (web/demo/style.css), light and dark. */
data class WebColors(
    val ink: Color,
    val muted: Color,
    val paper: Color,
    val panel: Color,
    val accent: Color,
    val line: Color,
)

private val LIGHT =
    WebColors(
        ink = Color(0xFF1D1D1F),
        muted = Color(0xFF6B6B70),
        paper = Color(0xFFFFFFFF),
        panel = Color(0xFFF4F4F6),
        accent = Color(0xFF2F5BD3),
        line = Color(0xFFD6D6DB),
    )

private val DARK =
    WebColors(
        ink = Color(0xFFECECF0),
        muted = Color(0xFFA0A0A8),
        paper = Color(0xFF16161A),
        panel = Color(0xFF222228),
        accent = Color(0xFF7E9BFF),
        line = Color(0xFF3A3A42),
    )

val LocalWebColors = staticCompositionLocalOf { LIGHT }

/** Body text is 15 px in the web demo. */
val BODY_SIZE = 15.sp

@Composable
fun WebTheme(content: @Composable () -> Unit) {
    val colors = if (isSystemInDarkTheme()) DARK else LIGHT
    CompositionLocalProvider(
        LocalWebColors provides colors,
        LocalTextStyle provides TextStyle(color = colors.ink, fontSize = BODY_SIZE),
        content = content,
    )
}

/** A button as the web demo draws them: panel background, thin border, 6 px corners. */
@Composable
fun WebButton(
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    content: @Composable () -> Unit,
) {
    val colors = LocalWebColors.current
    val shape = RoundedCornerShape(6.dp)
    Box(
        modifier
            .clip(shape)
            .background(colors.panel)
            .border(1.dp, colors.line, shape)
            .clickable(enabled = enabled, onClick = onClick)
            .padding(horizontal = 10.dp, vertical = 4.dp),
        contentAlignment = Alignment.Center,
    ) { content() }
}
