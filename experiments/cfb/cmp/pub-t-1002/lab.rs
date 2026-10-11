//! SK1 PUB-T-1002: temporary EXAMPLE, never a product image delivery path.
//! Uses the real pub-viewer and the pinned chaptera-image-decode-contract.
//! Source resources are never relabeled safe or copied into output JSON.
//! Derived data are kept in memory and destroyed before process exit.
use anyhow::{bail, Context, Result};
use chaptera_image_decode_contract::{
    decode_image_v1, DecodeLimitsV1, DecodePolicyV1, DecodedImageV1,
};
use jpeg_encoder::{ColorType as JpegColor, Encoder as JpegEncoder};
use png::{BitDepth, ColorType as PngColor, Encoder as PngEncoder};
use pub_viewer::{open_pub_bundle, viewer_geometry_environment_v0_1};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{env, fs, path::PathBuf};

const MAX_SOURCE_ENCODED_BYTES: usize = 5 * 1024 * 1024;
const MAX_PREVIEW_ENCODED_BYTES: usize = 5 * 1024 * 1024;
const MAX_AGGREGATE_DERIVED_BYTES: usize = 12 * 1024 * 1024;
const MAX_DIMENSION: u32 = 8192;
const MAX_PIXELS: u64 = 16_777_216;
const MAX_DECODED_BYTES: usize = 64 * 1024 * 1024;
const JPEG_QUALITY: u8 = 93;
const MAX_SAMPLE_POINTS: usize = 8192;

fn hex_hash(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

fn limits() -> DecodeLimitsV1 {
    DecodeLimitsV1 {
        max_encoded_bytes: MAX_SOURCE_ENCODED_BYTES,
        max_dimension_px: MAX_DIMENSION,
        max_total_pixels: MAX_PIXELS,
        max_decoded_bytes: MAX_DECODED_BYTES,
    }
}

fn encode_png(decoded: &DecodedImageV1) -> Result<Vec<u8>> {
    let color = match decoded.decoded_sample_model.as_str() {
        "gray" => PngColor::Grayscale,
        "gray_alpha" => PngColor::GrayscaleAlpha,
        "rgb" => PngColor::Rgb,
        "rgba" => PngColor::Rgba,
        other => bail!("unsupported_png_sample_model_{other}"),
    };
    if decoded.decoded_precision_bits != 8 {
        bail!("unsupported_png_precision");
    }
    let mut output = Vec::new();
    {
        let mut encoder = PngEncoder::new(
            &mut output,
            decoded.decoded_width_px,
            decoded.decoded_height_px,
        );
        encoder.set_color(color);
        encoder.set_depth(BitDepth::Eight);
        let mut writer = encoder.write_header().context("new PNG header")?;
        writer
            .write_image_data(&decoded.samples)
            .context("fresh PNG pixels")?;
    }
    Ok(output)
}

fn encode_jpeg(decoded: &DecodedImageV1) -> Result<Vec<u8>> {
    if decoded.decoded_precision_bits != 8 {
        bail!("unsupported_jpeg_precision");
    }
    let c = match decoded.decoded_sample_model.as_str() {
        "rgb" => JpegColor::Rgb,
        "gray" => JpegColor::Luma,
        other => bail!("unsupported_jpeg_sample_model_{other}"),
    };
    let width = u16::try_from(decoded.decoded_width_px)
        .context("jpeg width over u16 range")?;
    let height = u16::try_from(decoded.decoded_height_px)
        .context("jpeg height over u16 range")?;
    let mut output = Vec::new();
    JpegEncoder::new(&mut output, JPEG_QUALITY)
        .encode(&decoded.samples, width, height, c)
        .context("new JPEG from decoded samples")?;
    Ok(output)
}

fn no_carried_metadata(data: &[u8]) -> bool {
    !data.windows(6).any(|s| s == b"Exif\0\0")
        && !data.windows(10).any(|s| s == b"Photoshop ")
        && !data.windows(3).any(|s| s == b"XMP")
}

fn samples_difference(a: &DecodedImageV1, b: &DecodedImageV1) -> Result<Value> {
    if a.samples.len() != b.samples.len()
        || a.decoded_width_px != b.decoded_width_px
        || a.decoded_height_px != b.decoded_height_px
        || a.decoded_sample_model != b.decoded_sample_model
    {
        bail!("derived_raster_dimensions_or_samples_changed");
    }
    if a.samples.is_empty() {
        bail!("empty_samples");
    }
    let pixels = (u64::from(a.decoded_width_px) * u64::from(a.decoded_height_px)) as usize;
    let channels = a.samples.len() / pixels;
    if channels == 0 || pixels.checked_mul(channels) != Some(a.samples.len()) {
        bail!("unsupported_sample_layout");
    }
    let stride = pixels.div_ceil(MAX_SAMPLE_POINTS).max(1);
    let mut checked = 0u64;
    let mut changed = 0u64;
    let mut abs_sum = 0u64;
    let mut worst = 0u8;
    for index in (0..pixels).step_by(stride) {
        let base = index * channels;
        let mut pixel_max = 0;
        for component in 0..channels {
            let delta = a.samples[base + component].abs_diff(b.samples[base + component]);
            pixel_max = pixel_max.max(delta);
            worst = worst.max(delta);
            abs_sum += u64::from(delta);
        }
        changed += u64::from(pixel_max >= 12);
        checked += 1;
    }
    Ok(json!({
        "sampled_pixel_count": checked,
        "sampled_changed_pixel_fraction_threshold12": changed as f64 / checked as f64,
        "sampled_mean_abs_channel_delta": abs_sum as f64 / (checked * channels as u64) as f64,
        "sampled_max_channel_delta": worst,
        "sample_channels": channels,
        "png_pixel_lossless": a.mime_type=="image/png" && changed==0 && worst==0
    }))
}

fn build_preview(
    encoded: &[u8],
    mime: &str,
    cumulative: &mut usize,
) -> Result<Value> {
    let src_sha = hex_hash(encoded);
    let policy = DecodePolicyV1::reference();
    let input = decode_image_v1(
        encoded, mime, &src_sha, "source_color_untransformed_lab",
        &policy, &limits(),
    )
    .map_err(|err| anyhow::anyhow!("{}", err.code))?;
    if input.orientation_class != "normal" {
        bail!("unsupported_non_normal_exif_orientation");
    }
    if input.decoded_precision_bits != 8 {
        bail!("unsupported_source_high_precision");
    }
    let preview = match mime {
        "image/jpeg" => encode_jpeg(&input)?,
        "image/png" => encode_png(&input)?,
        _ => bail!("unsupported_source_preview_mime"),
    };
    if preview.is_empty() || preview.len() > MAX_PREVIEW_ENCODED_BYTES {
        bail!("preview_resource_byte_cap_exceeded");
    }
    if *cumulative + preview.len() > MAX_AGGREGATE_DERIVED_BYTES {
        bail!("document_aggregate_preview_byte_cap_exceeded");
    }
    if !no_carried_metadata(&preview) {
        bail!("preview_contains_forbidden_metadata_signature");
    }
    let derived_sha = hex_hash(&preview);
    if derived_sha == src_sha || preview == encoded {
        bail!("preview_byte_identical_to_original");
    }
    // Independent checksum verification on the newly coded artifact;
    // this does not constitute a browser-host trust decision.
    let output = decode_image_v1(
        &preview, mime, &derived_sha, "source_color_untransformed_lab",
        &policy, &limits(),
    )
    .map_err(|err| anyhow::anyhow!("{}", err.code))?;
    let delta = samples_difference(&input, &output)?;
    let preview_again = match mime {
        "image/jpeg" => encode_jpeg(&input)?,
        "image/png" => encode_png(&input)?,
        _ => unreachable!(),
    };
    if preview_again != preview {
        bail!("derived_encoder_not_deterministic");
    }
    *cumulative += preview.len();
    Ok(json!({
        "status": "encoded_candidate_only_not_browser_safe",
        "source_sha256": src_sha,
        "derived_sha256": derived_sha,
        "source_encoded_bytes": encoded.len(),
        "derived_encoded_bytes": preview.len(),
        "source_mime": mime,
        "derived_mime": mime,
        "width_px": input.decoded_width_px,
        "height_px": input.decoded_height_px,
        "source_decoder": input.decoder_id,
        "source_sample_model": input.decoded_sample_model,
        "exif_orientation": input.exif_orientation,
        "fresh_encoding_deterministic": true,
        "source_bytes_not_forwarded": true,
        "separate_derivative_identity": true,
        "metadata_stripped_by_reconstruction": true,
        "host_acceptance_not_executed": true,
        "pixel_comparison": delta
    }))
}

fn negative_controls() -> Result<Value> {
    let png_pixels = [
        255,0,0,128, 0,255,0,255,
        0,0,255,64, 255,255,0,0,
    ];
    let mut png = Vec::new();
    {
        let mut e = PngEncoder::new(&mut png, 2, 2);
        e.set_color(PngColor::Rgba);
        e.set_depth(BitDepth::Eight);
        // Synthetic valid source carries metadata that the new preview must shed.
        e.add_text_chunk("Comment".to_owned(), "source-origin-metadata".to_owned())?;
        let mut w = e.write_header()?;
        w.write_image_data(&png_pixels)?;
    }
    let policy = DecodePolicyV1::reference();
    let hash = hex_hash(&png);
    let expected_bad_hash = decode_image_v1(&png, "image/png", &"0".repeat(64),
        "color_untransformed_lab", &policy, &limits()).is_err();
    let mut tiny = limits();
    tiny.max_total_pixels = 1;
    let expected_pixel_cap = decode_image_v1(&png, "image/png", &hash,
        "color_untransformed_lab", &policy, &tiny).is_err();
    let truncated = png[..png.len()/2].to_vec();
    let expected_bad_png = decode_image_v1(&truncated, "image/png", &hex_hash(&truncated),
        "color_untransformed_lab", &policy, &limits()).is_err();
    let bad_type = decode_image_v1(&png, "image/svg+xml", &hash,
        "color_untransformed_lab", &policy, &limits()).is_err();
    let mut consumed = 0;
    let png_derivative = build_preview(&png, "image/png", &mut consumed)?;
    let expected_rgba = png_derivative["pixel_comparison"]["png_pixel_lossless"] == true;
    if !expected_bad_hash || !expected_pixel_cap || !expected_bad_png
        || !bad_type || !expected_rgba {
        bail!("negative_or_alpha_positive_contract_failed");
    }
    Ok(json!({
        "sha_mismatch_rejected": expected_bad_hash,
        "pixel_bomb_rejected": expected_pixel_cap,
        "corrupt_png_rejected": expected_bad_png,
        "unsupported_codec_rejected": bad_type,
        "transparent_rgba_png_roundtrip_exact": expected_rgba,
        "png_derivative_has_new_sha": png_derivative["source_sha256"] != png_derivative["derived_sha256"],
        "metadata_stripped": png_derivative["metadata_stripped_by_reconstruction"] == true
    }))
}

fn main() -> Result<()> {
    let mut args = env::args_os().skip(1);
    let pub_path = PathBuf::from(args.next().context("PUB file")?);
    let expected_source_hash = args.next().context("PUB expected hash")?.to_string_lossy().into_owned();
    let output = PathBuf::from(args.next().context("safe JSON output")?);
    if args.next().is_some(){ bail!("expected exactly three args"); }
    let raw = fs::read(&pub_path).context("read SHA pinned public original PUB")?;
    if hex_hash(&raw) != expected_source_hash {
        bail!("original_pub_sha256_mismatch");
    }
    let bundle = open_pub_bundle(&raw, viewer_geometry_environment_v0_1())
        .context("real RAR2 Viewer source geometry")?;
    let controls = negative_controls()?;
    let mut cumulative = 0usize;
    let mut results = Vec::new();
    for image in &bundle.geometry.images {
        if !image.source_exact {
            results.push(json!({
                "status": "derived_viewer_resource_unmodified",
                "mime": image.mime, "source_exact": false,
                "node_refs": image.node_ids.len(),
                "source_encoded_bytes": image.bytes.len()
            }));
            continue;
        }
        let outcome = match build_preview(&image.bytes, &image.mime, &mut cumulative) {
            Ok(mut candidate) => {
                candidate["node_refs"] = json!(image.node_ids.len());
                candidate["source_exact"] = json!(true);
                candidate
            },
            Err(error) => json!({
                "status": "fail_closed",
                "source_exact": true,
                "mime": image.mime,
                "source_encoded_bytes": image.bytes.len(),
                "node_refs": image.node_ids.len(),
                "code": error.to_string().split(':').next().unwrap_or("unknown").chars()
                    .take(72).collect::<String>()
            }),
        };
        results.push(outcome);
    }
    let accepted = results.iter().filter(|x|
        x["status"] == "encoded_candidate_only_not_browser_safe").count();
    let rejected = results.iter().filter(|x|x["status"]=="fail_closed").count();
    let non_source = results.iter().filter(|x|x["status"]=="derived_viewer_resource_unmodified").count();
    let report = json!({
        "schema":"sk1-pub-t1002-image-preview-candidate.v1",
        "product_pub_sha256":expected_source_hash,
        "product_pub_bytes":raw.len(),
        "viewer_engine":"real_pub_viewer_open_pub_bundle",
        "decode_engine":"chaptera-image-decode-contract/strict_sha+limits",
        "jpeg_encoder":"jpeg-encoder=0.7.1;quality=93",
        "png_encoder":"png=0.18.1;no_source_metadata",
        "contract_scope":"offline_experiment_not_product_or_browser",
        "fixed_limits":{
            "source_encoded_bytes":MAX_SOURCE_ENCODED_BYTES,
            "preview_encoded_bytes":MAX_PREVIEW_ENCODED_BYTES,
            "aggregate_preview_bytes":MAX_AGGREGATE_DERIVED_BYTES,
            "max_dimension":MAX_DIMENSION,
            "max_pixels":MAX_PIXELS,
            "max_decoded_bytes":MAX_DECODED_BYTES
        },
        "viewer_image_count":bundle.geometry.images.len(),
        "candidate_count":accepted,
        "failed_closed_count":rejected,
        "already_derived_viewer_count":non_source,
        "aggregate_preview_bytes":cumulative,
        "negative_controls":controls,
        "resources":results,
        "trust_host_sanitization_still_blocks_worker_images":true,
        "original_pub_or_image_bytes_exported":false
    });
    fs::write(output,serde_json::to_vec_pretty(&report)?)?;
    Ok(())
}
