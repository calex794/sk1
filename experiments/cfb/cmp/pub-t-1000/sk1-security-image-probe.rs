use anyhow::{Context, Result};
use pub_viewer::{open_pub_bundle, viewer_geometry_environment_v0_1};
use serde_json::{json, Value};
use std::{env, fs, path::PathBuf};

fn main() -> Result<()> {
    let mut argv = env::args_os().skip(1);
    let pub_path = PathBuf::from(argv.next().context("usage: sk1-security-image-probe PUB OUT")?);
    let out_path = PathBuf::from(argv.next().context("usage: sk1-security-image-probe PUB OUT")?);
    if argv.next().is_some() {
        anyhow::bail!("expected exactly two arguments");
    }
    let raw = fs::read(&pub_path).context("read public SHA-verified fixture")?;
    let bundle = open_pub_bundle(&raw, viewer_geometry_environment_v0_1())
        .context("open actual Reader pub-viewer source bundle")?;

    let images: Vec<Value> = bundle
        .geometry
        .images
        .iter()
        .map(|image| {
            json!({
                "mime": image.mime,
                "source_exact": image.source_exact,
                "raw_byte_len": image.bytes.len(),
                "scene_node_refs": image.node_ids.len(),
                "placement_count": image.placements.len(),
                "verified_source_sha_present": image.verified_source_sha256.is_some(),
                "security_browser_admission_class": if image.source_exact {
                    "source_exact_browser_denied"
                } else {
                    "derived_candidate_requires_other_host_and_byte_limits"
                }
            })
        })
        .collect();

    let data = json!({
        "schema": "sk1-pub-t1000-viewer-image-envelope.v1",
        "reader_engine": "real_pub_viewer_open_pub_bundle",
        "source_byte_len": raw.len(),
        "viewer_image_count": images.len(),
        "source_exact_image_count": images.iter()
            .filter(|x| x["source_exact"] == true).count(),
        "derived_candidate_image_count": images.iter()
            .filter(|x| x["source_exact"] == false).count(),
        "source_exact_raw_byte_total": images.iter()
            .filter(|x| x["source_exact"] == true)
            .filter_map(|x| x["raw_byte_len"].as_u64()).sum::<u64>(),
        "source_exact_node_refs": images.iter()
            .filter(|x| x["source_exact"] == true)
            .filter_map(|x| x["scene_node_refs"].as_u64()).sum::<u64>(),
        "images": images,
        "raw_bytes_emitted": false
    });
    fs::write(out_path,serde_json::to_vec_pretty(&data)?)?;
    Ok(())
}
