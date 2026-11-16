# QA report: CHANGES NEEDED

- ✅ **length** [en]: 39.1s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 39.1s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.3 LUFS, peak -1.5 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.3s (target <= 4s)
- ✅ **caption sync** [en]: 92 words, 34 caption events
- ✅ **visual licenses**: 7 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **visual_fit review** [en]: The visual queries for scenes 01 through 06 do not include the Lilac Chaser illusion, which is the core subject of the video. The narration asks the viewer to 'stare at the black dot' and 'watch the purple circles', but the stock queries are for 'black circle pulsing', 'binary code', 'male eye', 'clouds', 'green laser beams', and 'gears'. Fix: Source or generate a specific 'Lilac Chaser optical illusion' video clip for scenes 01-06 so the narration matches the visuals. → sent to visuals
- ❌ **people rule**: scene_07: visible are the hands and bare legs of a woman in all three frames. Replace with footage without women (a face-only close-up is the only exception). → sent to visuals