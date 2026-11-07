import type { VercelRequest, VercelResponse } from "@vercel/node";
import { prisma } from "./prisma";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    // 1. Seed YouTube Shorts from Engine History
    const short1 = await prisma.youtubeShort.upsert({
      where: { id: "20261102_171413_youtube_short" },
      update: {},
      create: {
        id: "20261102_171413_youtube_short",
        title: "AI Makes You Better at the Task, But Your Brain Learns Nothing",
        youtubeUrl: "https://youtube.com/shorts/20261102_171413_youtube_short",
        embedUrl: "https://www.youtube.com/embed/20261102_171413_youtube_short",
        topic: "Temporary Upskilling vs Genuine Learning",
        hookAngle: "Why relying on AI without self-testing leaves your brain at zero.",
        runId: "20261102_171413_youtube_short",
      },
    });

    const short2 = await prisma.youtubeShort.upsert({
      where: { id: "20261103_152749_youtube_short" },
      update: {},
      create: {
        id: "20261103_152749_youtube_short",
        title: "Why Nobody Noticed Your Mistake",
        youtubeUrl: "https://youtube.com/shorts/20261103_152749_youtube_short",
        embedUrl: "https://www.youtube.com/embed/20261103_152749_youtube_short",
        topic: "The Spotlight Effect & Social Anxiety",
        hookAngle: "Others notice your flaws 50% less than you think.",
        runId: "20261103_152749_youtube_short",
      },
    });

    // 2. Seed Initial Articles
    await prisma.post.upsert({
      where: { slug: "ai-makes-you-better-at-the-task-but-your-brain-learns-nothing" },
      update: {},
      create: {
        slug: "ai-makes-you-better-at-the-task-but-your-brain-learns-nothing",
        title: "AI Makes You Better at the Task, But Your Brain Learns Nothing",
        hook: "A randomized trial with 487 consultants revealed up to +49% performance gains with AI, but zero retention once the tool was removed.",
        summary: "Researchers term this 'temporary upskilling' — the cognitive illusion where external machine intelligence masks internal learning deficits.",
        contentMarkdown: `## The Psychological Paradox
When generative AI assists your work, you feel smarter. The prose flows, the code compiles, and the analysis looks executive-ready. But neuroscientists and behavioral economists call this the **cognitive offloading illusion**.

## What the Science Shows
In a landmark trial involving 487 management consultants, participants using generative models scored up to **+49 percentage points higher** on complex data-science tasks they had never previously performed. 

However, when the model was taken away, their performance dropped to the exact baseline of untrained novices. The brain had outsourced the encoding process, bypassing long-term potentiation in neural synapses.

## Daily Brain Bias Check
> **Reflection:** The next time you use AI to draft an email or solve a bug, ask yourself: *Could I explain the first principles of this solution on a whiteboard without looking at the screen?*

## Practical Takeaway
Always attempt the problem for 3 minutes yourself before prompting the model. Use AI as a harsh editor, not an intellectual crutch.`,
        coverImageUrl: "https://images.unsplash.com/photo-1618005182384-a83a8bd57fbe?auto=format&fit=crop&w=1200&q=80",
        imageCredit: "Milad Fakurian via Unsplash",
        tags: ["Cognitive Bias", "Human-AI Teaming", "Neuroscience", "Learning"],
        sourceUrls: ["https://arxiv.org/abs/2309.10691"],
        aiModelUsed: "Gemini 2.5 Flash",
        synthesisCostUsd: 0.00042,
        youtubeShortId: short1.id,
        status: "PUBLISHED",
      },
    });

    await prisma.post.upsert({
      where: { slug: "why-your-brain-overestimates-ai-the-automation-bias" },
      update: {},
      create: {
        slug: "why-your-brain-overestimates-ai-the-automation-bias",
        title: "Why Your Brain Overestimates AI: The Automation Bias",
        hook: "Humans are biologically wired to trust algorithmic outputs over human intuition — even when the model hallucinated.",
        summary: "Automation bias is the human tendency to favor machine-generated advice over contradictory human data, driven by cognitive energy conservation.",
        contentMarkdown: `## The Psychological Paradox
Why do pilots and doctors occasionally follow incorrect automated recommendations even when sensory alarms disagree? Behavioral psychologists call this **Automation Bias**.

## What the Science Shows
The human prefrontal cortex is an energy-conserving machine. Evaluating evidence from scratch consumes significant metabolic glucose. When an algorithmic suggestion arrives with high confidence, the brain's critical evaluation pathways suppress doubt.

## Daily Brain Bias Check
> **Reflection:** Do you find yourself accepting AI code or generated copy without verifying every edge case? That is your brain conserving glucose.

## Practical Takeaway
Introduce artificial friction: force yourself to identify at least one flaw in every AI-generated proposal before accepting it.`,
        coverImageUrl: "https://images.unsplash.com/photo-1620712943543-bcc4688e7485?auto=format&fit=crop&w=1200&q=80",
        imageCredit: "Google DeepMind via Unsplash",
        tags: ["Automation Bias", "Cognitive Science", "Machine Intelligence"],
        sourceUrls: ["https://psypost.org/automation-bias-study"],
        aiModelUsed: "Gemini 2.5 Flash",
        synthesisCostUsd: 0.00038,
        youtubeShortId: short2.id,
        status: "PUBLISHED",
      },
    });

    return res.status(200).json({ success: true, message: "Database seeded successfully!" });
  } catch (error: any) {
    console.error("Seed error:", error);
    return res.status(500).json({ error: error.message });
  }
}
