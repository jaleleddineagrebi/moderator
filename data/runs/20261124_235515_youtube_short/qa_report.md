# QA report: CHANGES NEEDED

- ✅ **length** [en]: 39.8s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 39.8s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.1 LUFS, peak -1.5 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.9s (target <= 4s)
- ✅ **caption sync** [en]: 103 words, 39 caption events
- ✅ **visual licenses**: 7 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **accuracy review** [en]: The scene 01 voiceover asks the user to name a vegetable 'right now', but scene 02 immediately says 'Don't blink' and 'Hacking your subconscious in ten seconds'. This is confusing because scene 05 is the actual moment the user should answer. Fix: Change scene 01 vo to 'Quick! Think of a vegetable...' and keep the prompt until the end. → sent to script
- ✅ **people rule**: no women beyond face close-ups in 7 scenes and 1 thumbnail(s)