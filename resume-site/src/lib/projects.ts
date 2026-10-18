import { projects } from "@/content/projects";
import type { Project } from "@/types/project";

export function getAllProjects(): Project[] {
  return [...projects].sort((a, b) => a.order - b.order);
}

export function getFlagshipProjects(): Project[] {
  return getAllProjects().filter((p) => p.depth === "flagship");
}

export function getSupportingProjects(): Project[] {
  return getAllProjects().filter((p) => p.depth === "supporting");
}

export function getProjectBySlug(slug: string): Project | undefined {
  return projects.find((p) => p.slug === slug);
}

export function getAllSlugs(): string[] {
  return projects.map((p) => p.slug);
}

export function getAdjacentProject(slug: string): Project | undefined {
  const all = getAllProjects();
  const index = all.findIndex((p) => p.slug === slug);
  if (index === -1) return undefined;
  return all[(index + 1) % all.length];
}

/** Other projects sharing at least one tag, excluding this one and the adjacent "next" project. */
export function getRelatedProjects(slug: string, limit = 2): Project[] {
  const current = getProjectBySlug(slug);
  if (!current) return [];

  const next = getAdjacentProject(slug);
  const excluded = new Set([slug, next?.slug].filter((s): s is string => Boolean(s)));

  return getAllProjects()
    .filter((p) => !excluded.has(p.slug))
    .map((p) => ({
      project: p,
      sharedCount: p.tags.filter((tag) => current.tags.includes(tag)).length,
    }))
    .filter((entry) => entry.sharedCount > 0)
    .sort((a, b) => b.sharedCount - a.sharedCount || a.project.order - b.project.order)
    .slice(0, limit)
    .map((entry) => entry.project);
}
