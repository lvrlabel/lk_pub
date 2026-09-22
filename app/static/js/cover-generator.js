/**
 * Генератор обложек в браузере (Canvas) — без Pillow на сервере.
 */
(function (global) {
    'use strict';

    var COVER_SIZE = 3000;
    var PREVIEW_SIZE = 800;
    var STYLES = {};

    function init(styles) {
        STYLES = styles || {};
    }

    function rgb(c) {
        return 'rgb(' + c[0] + ',' + c[1] + ',' + c[2] + ')';
    }

    function drawGradient(ctx, size, top, bottom) {
        var g = ctx.createLinearGradient(0, 0, 0, size);
        g.addColorStop(0, rgb(top));
        g.addColorStop(1, rgb(bottom));
        ctx.fillStyle = g;
        ctx.fillRect(0, 0, size, size);
    }

    function drawVinyl(ctx, size, preset) {
        drawGradient(ctx, size, preset.top, preset.bottom);
        var cx = size / 2;
        var cy = size / 2;
        var rOuter = size * 0.38;
        var rInner = size * 0.12;
        ctx.beginPath();
        ctx.arc(cx, cy, rOuter, 0, Math.PI * 2);
        ctx.fillStyle = 'rgb(40,40,40)';
        ctx.fill();
        ctx.lineWidth = Math.max(2, size / 500);
        ctx.strokeStyle = 'rgb(60,60,60)';
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(cx, cy, rInner, 0, Math.PI * 2);
        ctx.fillStyle = 'rgb(15,15,15)';
        ctx.fill();
    }

    function drawBgImage(ctx, size, img) {
        var w = img.naturalWidth || img.width;
        var h = img.naturalHeight || img.height;
        var side = Math.min(w, h);
        var sx = (w - side) / 2;
        var sy = (h - side) / 2;
        ctx.drawImage(img, sx, sy, side, side, 0, 0, size, size);
        ctx.fillStyle = 'rgba(0,0,0,0.45)';
        ctx.fillRect(0, 0, size, size);
    }

    function measureLines(ctx, lines, font) {
        ctx.font = font;
        return lines.map(function (line) {
            return ctx.measureText(line).width;
        });
    }

    function wrapText(ctx, text, maxWidth, font) {
        ctx.font = font;
        var words = (text || '').trim().split(/\s+/).filter(Boolean);
        if (!words.length) return [];
        var lines = [];
        var current = words[0];
        for (var i = 1; i < words.length; i++) {
            var trial = current + ' ' + words[i];
            if (ctx.measureText(trial).width <= maxWidth) {
                current = trial;
            } else {
                lines.push(current);
                current = words[i];
            }
        }
        lines.push(current);
        return lines;
    }

    function drawTextBlock(ctx, lines, font, yStart, boxW, boxH, fill, size) {
        if (!lines.length) return;
        ctx.font = font;
        ctx.fillStyle = fill;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'top';
        var titleSize = parseInt(font, 10) || Math.round(size * 0.09);
        var lineH = titleSize * 1.15;
        var totalH = lineH * lines.length;
        var y = yStart + Math.max(0, (boxH - totalH) / 2);
        var cx = boxW / 2;
        lines.forEach(function (line) {
            ctx.fillText(line, cx, y);
            y += lineH;
        });
    }

    function roundRectFill(ctx, x, y, w, h, r) {
        roundRect(ctx, x, y, w, h, r);
        ctx.fill();
    }

    function drawEqualizerMark(ctx, x, y, s) {
        var u = s / 34;
        var grad = ctx.createLinearGradient(x, y, x + s, y + s);
        grad.addColorStop(0, '#3b82f6');
        grad.addColorStop(1, '#1d4ed8');

        ctx.save();
        ctx.strokeStyle = grad;
        ctx.lineWidth = Math.max(1.5, 2.2 * u);
        roundRect(ctx, x + 2 * u, y, 30 * u, 34 * u, 9 * u);
        ctx.stroke();

        ctx.fillStyle = grad;
        [
            [9, 14, 4, 12],
            [16, 8, 4, 18],
            [23, 11, 4, 15]
        ].forEach(function (bar) {
            roundRectFill(ctx, x + bar[0] * u, y + bar[1] * u, bar[2] * u, bar[3] * u, 2 * u);
        });
        ctx.restore();
    }

    function drawBrandWatermark(ctx, size, preset, styleId) {
        var lightBg = styleId === 'minimal';
        var pad = size * 0.07;
        var iconSize = Math.max(32, Math.round(size * 0.052));
        var gap = Math.max(8, Math.round(size * 0.014));
        var brandSize = Math.max(18, Math.round(size * 0.03));
        var subSize = Math.max(11, Math.round(size * 0.016));
        var fontFamily = 'system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';

        ctx.font = '700 ' + brandSize + 'px ' + fontFamily;
        var brandText = 'TOOLLS';
        var brandW = ctx.measureText(brandText).width;
        ctx.font = '600 ' + subSize + 'px ' + fontFamily;
        var subText = 'MUSIC DISTRIBUTION';
        var subW = ctx.measureText(subText).width;

        var textBlockW = Math.max(brandW, subW);
        var textBlockH = brandSize + subSize * 1.05;
        var pillW = iconSize + gap + textBlockW + size * 0.036;
        var pillH = Math.max(iconSize, textBlockH) + size * 0.022;
        var pillX = (size - pillW) / 2;
        var pillY = size - pad - pillH;
        var radius = pillH * 0.42;

        ctx.save();
        ctx.globalAlpha = lightBg ? 0.92 : 0.78;
        ctx.fillStyle = lightBg ? 'rgba(255,255,255,0.96)' : 'rgba(15,23,42,0.88)';
        roundRectFill(ctx, pillX, pillY, pillW, pillH, radius);
        ctx.globalAlpha = 1;

        ctx.strokeStyle = lightBg ? 'rgba(148,163,184,0.45)' : 'rgba(255,255,255,0.14)';
        ctx.lineWidth = Math.max(1, size / 900);
        roundRect(ctx, pillX, pillY, pillW, pillH, radius);
        ctx.stroke();

        var iconX = pillX + size * 0.018;
        var iconY = pillY + (pillH - iconSize) / 2;
        drawEqualizerMark(ctx, iconX, iconY, iconSize);

        var textX = iconX + iconSize + gap;
        var textY = pillY + (pillH - textBlockH) / 2;
        ctx.textAlign = 'left';
        ctx.textBaseline = 'top';
        ctx.font = '700 ' + brandSize + 'px ' + fontFamily;
        ctx.fillStyle = lightBg ? 'rgb(15,23,42)' : 'rgb(248,250,252)';
        ctx.fillText(brandText, textX, textY);
        ctx.font = '600 ' + subSize + 'px ' + fontFamily;
        ctx.fillStyle = lightBg ? 'rgb(100,116,139)' : 'rgb(148,163,184)';
        ctx.fillText(subText, textX, textY + brandSize * 0.92);
        ctx.restore();
    }

    function roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    function loadBgImage(file) {
        if (!file || !file.size) {
            return Promise.resolve(null);
        }
        return new Promise(function (resolve, reject) {
            var url = URL.createObjectURL(file);
            var img = new Image();
            img.onload = function () {
                URL.revokeObjectURL(url);
                resolve(img);
            };
            img.onerror = function () {
                URL.revokeObjectURL(url);
                reject(new Error('bg load failed'));
            };
            img.src = url;
        });
    }

    function renderCover(canvas, opts) {
        var size = canvas.width;
        var ctx = canvas.getContext('2d');
        var preset = STYLES[opts.style] || STYLES.teal;
        var title = (opts.title || '').trim() || 'Название релиза';
        var artists = (opts.artists || '').trim() || 'Артист';

        return loadBgImage(opts.bgFile).then(function (bgImg) {
            if (bgImg) {
                drawBgImage(ctx, size, bgImg);
            } else if (preset.vinyl) {
                drawVinyl(ctx, size, preset);
            } else {
                drawGradient(ctx, size, preset.top, preset.bottom);
            }

            var pad = size * 0.1;
            var innerW = size - pad * 2;
            var innerH = size - pad * 2;
            var titleFont = '700 ' + Math.max(48, Math.round(size * 0.09)) + 'px system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
            var artistFont = '400 ' + Math.max(32, Math.round(size * 0.055)) + 'px system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';

            var titleLines = wrapText(ctx, title, innerW, titleFont);
            var artistLines = wrapText(ctx, artists, innerW, artistFont);
            var titleBlockH = innerH * 0.55;
            var artistBlockH = innerH - titleBlockH;

            drawTextBlock(ctx, titleLines, titleFont, pad, size, titleBlockH, rgb(preset.text), size);
            drawTextBlock(ctx, artistLines, artistFont, pad + titleBlockH, size, artistBlockH, rgb(preset.subtext), size);
            drawBrandWatermark(ctx, size, preset, opts.style);
        });
    }

    function canvasToBlob(canvas, quality) {
        return new Promise(function (resolve) {
            canvas.toBlob(function (blob) {
                resolve(blob);
            }, 'image/jpeg', quality || 0.92);
        });
    }

    function buildCanvas(size) {
        var canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        return canvas;
    }

    function safeFilename(title) {
        var name = (title || 'cover').replace(/[^\w\s\-а-яА-ЯёЁ]/gi, '_').trim().slice(0, 60);
        return name || 'cover';
    }

    global.CoverGenerator = {
        init: init,
        COVER_SIZE: COVER_SIZE,
        PREVIEW_SIZE: PREVIEW_SIZE,
        renderCover: renderCover,
        canvasToBlob: canvasToBlob,
        buildCanvas: buildCanvas,
        safeFilename: safeFilename
    };
})(window);
