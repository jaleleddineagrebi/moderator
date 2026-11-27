# QA report: CHANGES NEEDED

- ✅ **length** [en]: 39.2s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 39.2s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.2 LUFS, peak -2.4 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.3s (target <= 4s)
- ✅ **caption sync** [en]: 103 words, 38 caption events
- ✅ **visual licenses**: 7 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **accuracy review** [en]: In scene_01, the hook says 'You must stop picking the middle option', but the script explains the Decoy Effect where the middle option is intentionally unappealing so that buyers choose the most expensive option (the large), not the middle option. Fix scene_01 narration to match the decoy effect logic, e.g.: 'Companies love when you ignore the middle option.' or 'Here is why you always buy the most expensive option.' → sent to script
- ⚠️ **grammar review** [en]: In scene_07, ending with 'which is exactly why...' creates an awkward loop into scene_01 ('which is exactly why you must stop picking the middle option'), especially when combined with a call to action. Remove ', which is exactly why...' or adjust the loop transition so the CTA sentence stays clean and grammatical.
- ❌ **people rule**: scene_04: A woman wearing a headscarf/coat taking a photo is shown with her upper/full body visible among pedestrians in the middle frame.. Replace with footage without women (a face-only close-up is the only exception). → sent to visuals
- ❌ **people rule**: scene_05: Full body of a woman with long hair sitting on the grassy ridge overlooking the mountains.. Replace with footage without women (a face-only close-up is the only exception). → sent to visuals