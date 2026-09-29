/**
 * Ranking and result tiles, as training/src/glyphsketch/ranking.py (spec:
 * docs/export_format.md, "Pipeline of one query" and "Tiles").
 */

import type { CharacterInfo, Charset } from "./charset.ts";

export interface Candidate {
  codePoint: number;
  score: number;
  similarity: number;
}

export interface Tile {
  representative: number;
  /** The representative first, then the other members in chooser order. */
  members: number[];
  score: number;
}

export interface Ranking {
  similarities: Float32Array;
  scores: Float32Array;
  order: number[];
}

const SCRIPTS_ON_EVERY_KEYBOARD = new Set(["Common", "Inherited"]);

/** Digits, punctuation and symbols are on every keyboard; letters of script Common (𝐚) are not. */
export function onEveryKeyboard(info: CharacterInfo): boolean {
  return SCRIPTS_ON_EVERY_KEYBOARD.has(info.script) && !info.generalCategory.startsWith("L");
}

export class Ranker {
  readonly codePoints: Uint32Array;
  private readonly logPriors: Float32Array;
  private readonly groups: Int32Array;
  private readonly groupColumns = new Map<number, number[]>(); // group → columns
  private readonly infos: CharacterInfo[];
  private readonly weight: number;
  private readonly chooserCache = new Map<string, number[]>();

  constructor(codePoints: Uint32Array, charset: Charset) {
    this.codePoints = codePoints;
    this.weight = charset.priorWeight;
    this.infos = Array.from(codePoints, (codePoint) => {
      const info = charset.characters.get(codePoint);
      if (info === undefined) throw new Error(`No metadata for U+${codePoint.toString(16)}`);
      return info;
    });
    this.logPriors = Float32Array.from(this.infos, (info) => info.logPrior);
    this.groups = Int32Array.from(this.infos, (info) => info.group);
    this.groups.forEach((group, column) => {
      const list = this.groupColumns.get(group);
      if (list) list.push(column);
      else this.groupColumns.set(group, [column]);
    });
  }

  /** similarity + weight · log prior, per index column. */
  scores(similarities: Float32Array): Float32Array {
    const scores = new Float32Array(similarities.length);
    for (let column = 0; column < scores.length; column++) {
      scores[column] = similarities[column]! + this.weight * this.logPriors[column]!;
    }
    return scores;
  }

  /** Columns by decreasing score; ties keep index order. */
  order(scores: Float32Array): number[] {
    const columns = Array.from({ length: scores.length }, (_, column) => column);
    return columns.sort((a, b) => scores[b]! - scores[a]! || a - b);
  }

  /** Scores and the columns ordered by them: compute once, then take tiles and characters. */
  rank(similarities: Float32Array): Ranking {
    const scores = this.scores(similarities);
    return { similarities, scores, order: this.order(scores) };
  }

  topCharacters(ranking: Ranking | Float32Array, count: number): Candidate[] {
    const { similarities, scores, order } = ranking instanceof Float32Array ? this.rank(ranking) : ranking;
    return order.slice(0, count).map((column) => ({
      codePoint: this.codePoints[column]!,
      score: scores[column]!,
      similarity: similarities[column]!,
    }));
  }

  /** A group's members in code point order. */
  members(group: number): number[] {
    const columns = this.groupColumns.get(group);
    if (!columns) throw new Error(`Unknown group ${group}`);
    return columns.map((column) => this.codePoints[column]!).sort((a, b) => a - b);
  }

  chooser(group: number, scripts: readonly string[]): number[] {
    const key = `${group}|${scripts.join(",")}`;
    const cached = this.chooserCache.get(key);
    if (cached) return cached;
    const typed = (column: number): boolean => {
      const info = this.infos[column]!;
      return scripts.includes(info.script) || onEveryKeyboard(info);
    };
    const columns = [...this.groupColumns.get(group)!].sort(
      (a, b) =>
        Number(!typed(a)) - Number(!typed(b)) ||
        this.logPriors[b]! - this.logPriors[a]! ||
        this.codePoints[a]! - this.codePoints[b]!,
    );
    const result = columns.map((column) => this.codePoints[column]!);
    this.chooserCache.set(key, result);
    return result;
  }

  tiles(ranking: Ranking | Float32Array, count: number, scripts: readonly string[]): Tile[] {
    const { scores, order } = ranking instanceof Float32Array ? this.rank(ranking) : ranking;
    const tiles: Tile[] = [];
    const seen = new Set<number>();
    for (const column of order) {
      const group = this.groups[column]!;
      if (seen.has(group)) continue;
      seen.add(group);
      const members = this.chooser(group, scripts);
      tiles.push({ representative: members[0]!, members, score: scores[column]! });
      if (tiles.length === count) break;
    }
    return tiles;
  }
}
