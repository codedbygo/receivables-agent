import { describe, expect, it } from "vitest";
import { ChannelPlan } from "./schemas";

// HACK-004 (QA ISSUE-014): the dialog started from "not agreed" because the plan carried no consent.
describe("ChannelPlan", () => {
  it("keeps what the customer agreed to, so the preferences dialog can start from it", () => {
    const plan = ChannelPlan.parse({
      preferred_channel: "whatsapp",
      last_channel: null,
      last_contact_on: null,
      response_status: "never contacted",
      cadence_day: 1,
      recommended_channel: "email",
      draft_channel: "email",
      next_step_channel: null,
      next_step_on: null,
      factors: [],
      consent: { whatsapp: true, sms: false, voice: true },
    });

    expect(plan.consent).toEqual({ whatsapp: true, sms: false, voice: true });
  });
});
