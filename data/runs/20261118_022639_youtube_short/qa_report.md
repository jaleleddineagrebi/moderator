# QA report: CHANGES NEEDED

- ✅ **length** [en]: 37.0s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 37.0s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.5 LUFS, peak -1.4 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 3.8s (target <= 4s)
- ⚠️ **hook sharpness** [en]: scene_01 is 3.8s (tighter <3.5s performs better)
- ✅ **caption sync** [en]: 90 words, 35 caption events
- ✅ **visual licenses**: 7 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **grammar review** [en]: The narration in scene_07 is an incomplete sentence: 'Your eyes are lying, so you should'. Fix: Remove 'so you should' or change it to 'Your eyes are lying. Subscribe for more.' → sent to script
- ⚠️ **accuracy review** [en]: Scene 06 refers to a 'grey void' but the visual query is for 'grey smoke cloud', which may look like smoke rather than a solid grey field required for the Troxler effect. Change query to 'solid flat grey background'.
- ✅ **people rule**: no women beyond face close-ups in 7 scenes and 1 thumbnail(s)