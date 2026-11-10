# QA report: CHANGES NEEDED

- ✅ **length** [en]: 47.8s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 47.8s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.4 LUFS, peak -1.5 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.3s (target <= 4s)
- ✅ **caption sync** [en]: 113 words, 42 caption events
- ✅ **visual licenses**: 7 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ⚠️ **accuracy review** [en]: In scene_03, photoreceptors don't become 'numb'; they undergo 'neural adaptation' or 'bleaching'. The term 'numb' is slightly misleading for biological processes. Change 'becoming numb to' to 'adapting to'.
- ❌ **visual_fit review** [en]: The script instructs the viewer to 'stare at this red dot', but the visual source query for scene_01 is 'macro eye iris'. The viewer needs to see the dot to stare at it. Change the query to 'bright red circle on white background' or similar. → sent to visuals
- ⚠️ **grammar review** [en]: In scene_07, the phrase 'which is why you must...' is a dangling fragment intended for looping, but it creates a non-sequitur following the previous instruction. Suggest ending with 'if you saw it!' to keep it punchy and removing the loop lead-in if it doesn't resolve to the start.
- ✅ **people rule**: no women beyond face close-ups in 7 scenes and 1 thumbnail(s)