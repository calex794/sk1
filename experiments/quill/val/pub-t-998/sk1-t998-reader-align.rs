// Scientific probe compiled against an unmodified pinned real RAR2 checkout.
// The generated JSON contains no Story text or original/candidate PUB bytes.
use anyhow::{Context, Result};
use pub_viewer::{open_pub_geometry, viewer_geometry_environment_v0_1};
use serde_json::json;
use std::{env, fs, path::PathBuf};

fn main() -> Result<()> {
    let mut args = env::args_os().skip(1);
    let input = PathBuf::from(args.next().context("expected PUB input")?);
    let output = PathBuf::from(args.next().context("expected private JSON output")?);
    if args.next().is_some() {
        anyhow::bail!("expected exactly input and output");
    }
    let bytes = fs::read(&input).context("read disposable public PUB")?;
    let receipt = match open_pub_geometry(&bytes, viewer_geometry_environment_v0_1()) {
        Ok(model) => {
            let stories: Vec<_> = model.document.stories.iter()
                .map(|story| json!({
                    "utf16_units": story.text.encode_utf16().count(),
                    "scalars": story.text.chars().count()
                })).collect();
            let runs: Vec<_> = model.paragraph_alignments.iter()
                .map(|run| {
                    let associated_story = model.document.stories.iter()
                        .find(|story| story.id == run.story_id);
                    let applicable = associated_story
                        .map(|story| run.applies_to_story_text(&story.text))
                        .unwrap_or(false);
                    json!({
                        "story_utf16_units": associated_story
                            .map(|story| story.text.encode_utf16().count()),
                        "story_scalars": associated_story
                            .map(|story| story.text.chars().count()),
                        "scalar_start": run.scalar_start,
                        "scalar_end": run.scalar_end,
                        "alignment": format!("{:?}", run.alignment),
                        "source_value": run.source_value,
                        "applies_to_original_story_text": applicable
                    })
                }).collect();
            json!({
                "opened": true,
                "pages": model.document.pages.len(),
                "stories": stories,
                "paragraph_alignments": runs,
                "text_fragment_count": model.text_fragments.len(),
                "diagnostic_codes": model.document.diagnostics.iter()
                    .map(|diagnostic| diagnostic.code.as_str()).collect::<Vec<_>>()
            })
        }
        Err(_) => json!({"opened": false, "error_class": "reader_open_failed"})
    };
    fs::write(output, serde_json::to_vec(&receipt)?)?;
    Ok(())
}
