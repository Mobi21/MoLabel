/**
 * Tests for PluginComponentLoader (PL-015 Tier 2).
 */

import { describe, it, expect } from "vitest"

import {
  invalidatePluginComponent,
  clearPluginComponentCache,
} from "./PluginComponentLoader"
import type { PluginComponentManifest } from "@/types/plugin-ui"

// Note: Full rendering tests for PluginComponentLoader require
// mocking dynamic imports which is complex in vitest. We test
// the utility functions and type contracts here. The actual
// dynamic loading is covered by E2E tests.

describe("PluginComponentLoader utilities", () => {
  it("invalidatePluginComponent does not throw", () => {
    expect(() => invalidatePluginComponent("test.plugin")).not.toThrow()
  })

  it("invalidatePluginComponent with slot does not throw", () => {
    expect(() =>
      invalidatePluginComponent("test.plugin", "record_renderer"),
    ).not.toThrow()
  })

  it("clearPluginComponentCache does not throw", () => {
    expect(() => clearPluginComponentCache()).not.toThrow()
  })
})

describe("PluginComponentManifest type contract", () => {
  it("accepts valid manifest object", () => {
    const manifest: PluginComponentManifest = {
      pluginId: "molabel.test.plugin",
      pluginVersion: "1.0.0",
      slot: "record_renderer",
      bundlePath: "renderer.mjs",
    }
    expect(manifest.pluginId).toBe("molabel.test.plugin")
    expect(manifest.pluginVersion).toBe("1.0.0")
    expect(manifest.slot).toBe("record_renderer")
    expect(manifest.bundlePath).toBe("renderer.mjs")
  })

  it("supports all defined component slots", () => {
    const slots = [
      "record_renderer",
      "review_form",
      "detail_panel",
      "dashboard_panel",
      "custom_screen",
    ] as const

    for (const slot of slots) {
      const manifest: PluginComponentManifest = {
        pluginId: "test",
        pluginVersion: "1.0.0",
        slot,
        bundlePath: "component.mjs",
      }
      expect(manifest.slot).toBe(slot)
    }
  })
})
