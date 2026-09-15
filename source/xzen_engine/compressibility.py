from __future__ import annotations

import os
from typing import Dict, Any, Tuple
from .formatting import format_game_size

# Pre-packaged dense archive extensions that yield negligible/zero NTFS compression savings
ARCHIVE_EXTENSIONS = {
    ".pak", ".vpk", ".zip", ".rar", ".7z", ".tar", ".gz", ".xz", ".bz2",
    ".unity3d", ".assetbundle", ".ba2", ".bsa", ".bik", ".bk2", ".bnk",
    ".pck", ".forge", ".rgk", ".bnd", ".bnd4", ".pkg", ".bundle",
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".webm",
    ".mp3", ".ogg", ".aac", ".flac", ".wma", ".m4a", ".opus",
}

# High-yield uncompressed or lightly compressed extensions
HIGH_COMPRESSIBILITY_EXTENSIONS = {
    # Uncompressed / Raw Text & Scripts
    ".txt", ".json", ".xml", ".ini", ".csv", ".log", ".lua", ".py", ".cfg",
    ".html", ".htm", ".css", ".js", ".ts", ".yaml", ".yml", ".proto",
    # Uncompressed Textures & Buffers
    ".dds", ".tga", ".bmp", ".raw", ".obj", ".fbx", ".dae", ".blend",
    # Uncompressed Audio
    ".wav", ".aiff", ".pcm",
    # Binaries, Shaders & Map data
    ".dll", ".exe", ".so", ".dylib", ".cso", ".spv", ".hlsl", ".glsl", ".map", ".pdb", ".dat",
}


def analyze_directory_compressibility(
    folder_path: str,
    max_sampled_files: int = 500,
) -> Dict[str, Any]:
    """
    Fast directory sampler that checks file extensions and structural metadata
    to calculate a compressibility traffic light rating and estimated savings preview.
    """
    if not folder_path or not os.path.exists(folder_path):
        return {
            "status": "unknown",
            "traffic_light": "gray",
            "rating_text": "Unknown",
            "estimated_savings_ratio": 0.0,
            "estimated_savings_bytes": 0,
            "savings_preview_text": "No Data",
            "details": "Folder does not exist or cannot be accessed.",
        }

    total_sampled_size = 0
    high_yield_size = 0
    archive_size = 0
    other_size = 0
    file_count = 0

    try:
        for root, _, files in os.walk(folder_path):
            for filename in files:
                file_count += 1
                file_path = os.path.join(root, filename)
                try:
                    size = os.path.getsize(file_path)
                except Exception:
                    size = 0

                total_sampled_size += size
                ext = os.path.splitext(filename)[1].lower()

                if ext in ARCHIVE_EXTENSIONS:
                    archive_size += size
                elif ext in HIGH_COMPRESSIBILITY_EXTENSIONS:
                    high_yield_size += size
                else:
                    other_size += size

                if file_count >= max_sampled_files:
                    break
            if file_count >= max_sampled_files:
                break
    except Exception as exc:
        return {
            "status": "error",
            "traffic_light": "gray",
            "rating_text": "Error",
            "estimated_savings_ratio": 0.0,
            "estimated_savings_bytes": 0,
            "savings_preview_text": "Error",
            "details": str(exc),
        }

    if total_sampled_size <= 0:
        return {
            "status": "empty",
            "traffic_light": "yellow",
            "rating_text": "Empty/Small",
            "estimated_savings_ratio": 0.0,
            "estimated_savings_bytes": 0,
            "savings_preview_text": "Saves ~0 B",
            "details": "No files found to sample.",
        }

    archive_ratio = archive_size / total_sampled_size
    high_yield_ratio = high_yield_size / total_sampled_size

    # Estimated savings ratio formula:
    # High-yield files typically compress by ~45-60% (LZX / XPRESS)
    # Other miscellaneous binaries/assets compress by ~15-25%
    # Archive files compress by ~1-3%
    estimated_ratio = (high_yield_ratio * 0.50) + ((other_size / total_sampled_size) * 0.20) + (archive_ratio * 0.02)
    estimated_ratio = max(0.01, min(0.70, estimated_ratio))

    # Traffic light determination
    if archive_ratio >= 0.65:
        traffic_light = "red"
        rating_text = "Low Yield (Pre-compressed/Packed)"
    elif high_yield_ratio >= 0.40 or (archive_ratio < 0.35 and estimated_ratio >= 0.25):
        traffic_light = "green"
        rating_text = "High Savings Potential"
    else:
        traffic_light = "yellow"
        rating_text = "Moderate Savings Potential"

    return {
        "status": "ok",
        "traffic_light": traffic_light,
        "rating_text": rating_text,
        "estimated_savings_ratio": estimated_ratio,
        "archive_ratio": archive_ratio,
        "high_yield_ratio": high_yield_ratio,
        "sampled_files": file_count,
        "total_sampled_size": total_sampled_size,
    }


def calculate_savings_preview(
    game: Dict[str, Any],
    analysis: Dict[str, Any] | None = None,
) -> Tuple[str, str, str]:
    """
    Returns (traffic_light, badge_text, savings_preview_text) for a given game dictionary.
    """
    compressed_size = int(game.get("compressed_size", 0) or 0)
    original_size = int(game.get("size", 0) or game.get("manifest_size", 0) or 0)

    # If already compressed, display verified actual savings
    if compressed_size > 0 and original_size > compressed_size:
        actual_saved = original_size - compressed_size
        return "green", "Compressed", f"Saved {format_game_size(actual_saved)}"

    # If cached analysis exists in game dict or provided
    cached = analysis or game.get("compressibility_analysis")
    if not cached:
        folder_path = game.get("path", "")
        if folder_path and os.path.exists(folder_path):
            cached = analyze_directory_compressibility(folder_path)
        else:
            return "gray", "Unknown", "No Data"

    traffic_light = cached.get("traffic_light", "yellow")
    ratio = cached.get("estimated_savings_ratio", 0.25)
    est_bytes = int(original_size * ratio) if original_size > 0 else 0

    if est_bytes > 0:
        preview_text = f"Saves ~{format_game_size(est_bytes)}"
    else:
        preview_text = f"Est. ~{int(ratio * 100)}% savings"

    badge_text = cached.get("rating_text", "Analyzed")
    return traffic_light, badge_text, preview_text
