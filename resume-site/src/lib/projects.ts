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
