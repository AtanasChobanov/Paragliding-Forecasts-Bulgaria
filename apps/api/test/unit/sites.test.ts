import type { SiteRepository } from "../../src/modules/sites/site.repository.js";
import { InMemorySiteRepository } from "../../src/modules/sites/in-memory-site.repository.js";
import { SiteService } from "../../src/modules/sites/site.service.js";
import { describe, expect, it, vi } from "vitest";

describe("site catalog", () => {
  it("returns the seven initial Bulgarian locations in a stable order", async () => {
    const repository = new InMemorySiteRepository();

    await expect(repository.list()).resolves.toEqual([
      { id: 1, slug: "sofia-vitosha-kominite", name: "Sofia - Vitosha (Kominite)" },
      { id: 2, slug: "zlatitsa", name: "Zlatitsa" },
      { id: 3, slug: "sopot", name: "Sopot" },
      { id: 4, slug: "nevsha", name: "Nevsha" },
      { id: 5, slug: "shumen", name: "Shumen" },
      { id: 6, slug: "pastrona", name: "Pastrona" },
      { id: 7, slug: "dobrich-region", name: "Dobrich region" },
    ]);
  });

  it("looks up a known site without exposing mutable repository state", async () => {
    const repository = new InMemorySiteRepository();
    const first = await repository.findBySlug("sopot");

    expect(first).toEqual({ id: 3, slug: "sopot", name: "Sopot" });
    if (first !== undefined) {
      first.name = "Changed outside the repository";
    }

    await expect(repository.findBySlug("sopot")).resolves.toEqual({
      id: 3,
      slug: "sopot",
      name: "Sopot",
    });
  });

  it("rejects duplicate numeric site identifiers", () => {
    expect(
      () =>
        new InMemorySiteRepository([
          { id: 3, slug: "sopot", name: "Sopot" },
          { id: 3, slug: "other-sopot", name: "Duplicate Sopot" },
        ]),
    ).toThrow("Duplicate site ID: 3");
  });

  it("rejects duplicate site slugs", () => {
    expect(
      () =>
        new InMemorySiteRepository([
          { id: 3, slug: "sopot", name: "Sopot" },
          { id: 8, slug: "sopot", name: "Duplicate Sopot" },
        ]),
    ).toThrow("Duplicate site slug: sopot");
  });

  it("keeps the service dependent on the repository port", async () => {
    const site = { id: 3, slug: "sopot", name: "Sopot" };
    const list = vi.fn().mockResolvedValue([site]);
    const findBySlug = vi.fn().mockResolvedValue(site);
    const repository: SiteRepository = {
      list,
      findBySlug,
    };
    const service = new SiteService(repository);

    await expect(service.listSites()).resolves.toEqual([site]);
    await expect(service.findSiteBySlug("sopot")).resolves.toEqual(site);
    expect(list).toHaveBeenCalledOnce();
    expect(findBySlug).toHaveBeenCalledWith("sopot");
  });
});
