    #[test]
    fn apache_poi_sample3_opaque_stsh_and_font_survive_story_shrink() {
        // Real Rust Writer test, not a native Publisher oracle.
        // Uses only the pre-existing PUBLIC Apache POI Sample3 fixture.
        let source_pub = decode_base64(include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/tests/fixtures/Sample3.pub.b64"
        )));
        let original =
            pub_cfb::read_stream_reader(Cursor::new(source_pub), STREAM).expect("source Quill");
        let original_catalog =
            parse_confirmed_story_catalog(StreamPath(STREAM.into()), &original)
                .expect("source Story catalog");
        let stsh1 = all_descriptors(&original_catalog)
            .into_iter()
            .find(|d| d.name.value == *b"STSH" && d.option_a.value == 1)
            .expect("STSH1");
        let stsh1_start = stsh1.data_offset.value as usize;
        assert_eq!(stsh1.data_length.value, 440);
        assert_eq!(
            read_u32(&original, stsh1_start + 4).expect("STSH1 record count"),
            2
        );
        let paragraph_start = stsh1_start
            + 20
            + read_u32(&original, stsh1_start + 24).expect("record offset") as usize;
        assert_eq!(stsh1_start + 440 - paragraph_start, 12);
        // The only declared paragraph property is id0x30, not id0x13.
        assert!(
            &original[paragraph_start + 6..paragraph_start + 10]
                == &[0x30, 0x12, 0x05, 0x00],
            "unexpected pinned Sample3 paragraph style structure"
        );

        for mutate_opaque in [false, true] {
            let mut input = original.clone();
            if mutate_opaque {
                // Synthetic IN-MEMORY counterexample: no 0x13, nonzero 0x30 high.
                input[paragraph_start + 9] = 0x5a;
                // Break shared STSH/FONT u32@+8 equality without changing length.
                input[stsh1_start + 8] ^= 0x5a;
                assert!(
                    &input[paragraph_start + 6..paragraph_start + 10]
                        == &[0x30, 0x12, 0x05, 0x5a],
                    "id0x30 in-memory guard"
                );
                let changed = input.iter().zip(original.iter())
                    .filter(|(a, b)| a != b).count();
                assert_eq!(changed, 2, "only two opaque physical bytes are changed");
            }

            let before =
                parse_confirmed_story_catalog(StreamPath(STREAM.into()), &input)
                    .expect("mutated input must remain Story-readable");
            let story = before.stories.iter()
                .find(|story| story.syid == QuillSyid(4))
                .expect("Sample3 Story SYID4");
            let units = utf16_units(&story.utf16le).expect("UTF16");
            let deleted: Vec<u16> = "345678".encode_utf16().collect();
            let start = units.windows(deleted.len())
                .position(|window| window == deleted)
                .expect("controlled deletion marker");
            let plan = plan_quill_story_text_edit(
                StreamPath(STREAM.into()),
                &input,
                &QuillStoryTextEdit {
                    story_syid: QuillSyid(4),
                    start_utf16: u32::try_from(start).expect("index"),
                    delete_utf16: u32::try_from(deleted.len()).expect("length"),
                    replacement: String::new(),
                },
            ).expect("real bounded Rust Writer should permit -6 deletion");
            assert_eq!(plan.delta_bytes, -12, "TEXT must shrink by 12B");
            let after =
                parse_confirmed_story_catalog(StreamPath(STREAM.into()), &plan.output_stream)
                    .expect("writer output Story catalog");

            let source_descriptors = all_descriptors(&before);
            let output_descriptors = all_descriptors(&after);
            assert_eq!(source_descriptors.len(), output_descriptors.len());
            let mut checked_stsh = 0usize;
            let mut checked_font = 0usize;
            for (index, (a, b)) in source_descriptors.iter()
                .zip(output_descriptors.iter()).enumerate()
            {
                assert_eq!(a.name.value, b.name.value, "descriptor order");
                assert_eq!(a.option_a.value, b.option_a.value, "descriptor subtype");
                if a.name.value != *b"STSH" && a.name.value != *b"FONT" {
                    continue;
                }
                assert_eq!(a.data_length.value, b.data_length.value, "payload length");
                let i = a.data_offset.value as usize;
                let j = b.data_offset.value as usize;
                let n = a.data_length.value as usize;
                // Use assert!, not assert_eq!, to avoid dumping payload bytes in CI logs.
                assert!(
                    &input[i..i+n] == &plan.output_stream[j..j+n],
                    "opaque payload not preserved at descriptor index {index}"
                );
                if a.name.value == *b"STSH" {
                    assert_eq!(
                        b.data_offset.value as i64 - a.data_offset.value as i64,
                        -12, "STSH relative relocation"
                    );
                    checked_stsh += 1;
                } else {
                    assert_eq!(b.data_offset.value, a.data_offset.value,
                        "FONT must remain anchored");
                    checked_font += 1;
                }
            }
            assert_eq!(checked_stsh, 3, "expected exactly three STSH chunks");
            assert_eq!(checked_font, 1, "expected exactly one FONT chunk");
        }
    }

