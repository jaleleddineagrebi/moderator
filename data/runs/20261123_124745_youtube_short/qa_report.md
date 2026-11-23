# QA report: CHANGES NEEDED

- ✅ **length** [en]: 38.8s (must be under 60s; target 32-50s)
- ✅ **target length** [en]: 38.8s
- ✅ **aspect ratio** [en]: 1080x1920
- ✅ **video codec** [en]: h264
- ✅ **audio track** [en]: present
- ✅ **loudness** [en]: -14.0 LUFS, peak -1.8 dBFS (target -14 LUFS, peak <= -1)
- ✅ **hook timing** [en]: scene_01 spoken in 2.5s (target <= 4s)
- ✅ **caption sync** [en]: 99 words, 36 caption events
- ✅ **visual licenses**: 8 assets: pixabay
- ✅ **visual diversity**: all scenes use distinct footage
- ✅ **audio licenses**: music: original work, no third-party rights; sfx: original work, no third-party rights; voice: synthetic voice; no third-party performance rights
- ❌ **accuracy review** [en]: The code ##002# does not wipe 'all active settings' or 'reset entire phone privacy' on iPhones as implied; it specifically disables call forwarding. The script overstates its security impact which can be misleading. Change 'wipes all active forwarding settings' to 'disables active call forwarding' and 'resets your entire phone privacy' to 'disables external forwarding'. → sent to script
- ⚠️ **visual_fit review** [en]: Scene 04 visual query 'cctv camera rotating' is too literal for privacy. Change query to 'smartphone lock screen' or 'security shield icon' to better match the 'privacy reset' topic.
- ⚠️ **metadata review** [en]: The description asks to 'Comment YES or NO', but the script in Scene 07 asks to 'comment SAFE'. Align the description to say 'Comment SAFE' for consistency.
- ✅ **people rule**: no women beyond face close-ups in 8 scenes and 1 thumbnail(s)