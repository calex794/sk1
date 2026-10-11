// Hosted-only comparison probe. Written into a disposable pinned RAR2 checkout.
// Raw text stays in the CI temporary directory and is never published.
use anyhow::{Context, Result};
use pub_viewer::{open_pub_geometry, viewer_geometry_environment_v0_1};
use serde_json::json;
use std::{env, fs, path::PathBuf};

fn main() -> Result<()> {
    let mut argv = env::args_os().skip(1);
    let input = PathBuf::from(argv.next().context("usage: sk1-compare-reader-text PUB OUT")?);
    let output = PathBuf::from(argv.next().context("usage: sk1-compare-reader-text PUB OUT")?);
    if argv.next().is_some() {
        anyhow::bail!("expected exactly two arguments");
    }
    let bytes = fs::read(&input).context("read public source")?;
    let value = match open_pub_geometry(&bytes, viewer_geometry_environment_v0_1()) {
        Ok(model) => json!({
            "opened": true,
            "pages": model.document.pages.len(),
            "stories": model.document.stories.iter()
                .map(|story| story.text.as_str()).collect::<Vec<_>>(),
            "story_frame_count": model.story_frames.len(),
            "text_fragment_count": model.text_fragments.len(),
            "paragraph_alignment_runs": model.paragraph_alignments.len(),
            "paragraph_line_spacing_runs": model.paragraph_line_spacings.len(),
            "paragraph_flow_runs": model.paragraph_flow_runs.len(),
            "typography_runs": model.typography_runs.len(),
            "tables": model.tables.len(),
            "image_resources": model.images.len(),
            "image_placements": model.images.iter().map(|x| x.node_ids.len()).sum::<usize>(),
            "shape_scene_nodes": model.scene.nodes.len(),
            "paints": model.paints.len(),
            "diagnostic_count": model.document.diagnostics.len(),
        }),
        Err(_) => json!({"opened": false}),
    };
    fs::write(&output, serde_json::to_vec(&value)?)?;
    Ok(())
}
