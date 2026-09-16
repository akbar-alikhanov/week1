import { ValidationError } from "@/shared/errors/app-error";
import { XP_PER_LEVEL } from "@/shared/constants/gamification";

export interface UserProps {
  id: string;
  name: string;
  email: string;
  passwordHash: string | null;
  image: string | null;
  level: number;
  xp: number;
  currentStreak: number;
  longestStreak: number;
  lastActivityAt: Date | null;
  createdAt: Date;
}

/** Level N requires (N-1) * XP_PER_LEVEL total XP. */
export function levelForXp(xp: number): number {
  return Math.floor(xp / XP_PER_LEVEL) + 1;
}

export function xpIntoCurrentLevel(xp: number): number {
  return xp % XP_PER_LEVEL;
}

/**
 * Rich domain entity for the learner. Owns the gamification rules (XP,
 * leveling, streaks) so they live in one framework-free place instead of
 * being re-derived ad hoc across use cases.
 */
export class User {
  private constructor(private props: UserProps) {}

  static create(props: UserProps): User {
    if (!props.name.trim()) {
      throw new ValidationError("Name is required.");
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(props.email)) {
      throw new ValidationError("A valid email is required.");
    }
    return new User(props);
  }

  get id() {
    return this.props.id;
  }
  get name() {
    return this.props.name;
  }
  get email() {
    return this.props.email;
  }
  get passwordHash() {
    return this.props.passwordHash;
  }
  get image() {
    return this.props.image;
  }
  get xp() {
    return this.props.xp;
  }
  get level() {
    return this.props.level;
  }
  get currentStreak() {
    return this.props.currentStreak;
  }
  get longestStreak() {
    return this.props.longestStreak;
  }
  get lastActivityAt() {
    return this.props.lastActivityAt;
  }

  /** Returns a new User with XP added and level recomputed. */
  addXp(amount: number): User {
    if (amount <= 0) {
      throw new ValidationError("XP awarded must be a positive amount.");
    }
    const xp = this.props.xp + amount;
    return new User({ ...this.props, xp, level: levelForXp(xp) });
  }

  /**
   * Records activity for "now" and returns a new User with the streak
   * updated: +1 if the last activity was yesterday, unchanged if it was
   * already today, reset to 1 otherwise.
   */
  recordActivity(now: Date = new Date()): User {
    const today = startOfDay(now);
    const last = this.props.lastActivityAt ? startOfDay(this.props.lastActivityAt) : null;

    let currentStreak = this.props.currentStreak;
    if (!last) {
      currentStreak = 1;
    } else {
      const dayDiff = Math.round((today.getTime() - last.getTime()) / 86_400_000);
      if (dayDiff === 0) {
        currentStreak = this.props.currentStreak || 1;
      } else if (dayDiff === 1) {
        currentStreak = this.props.currentStreak + 1;
      } else {
        currentStreak = 1;
      }
    }

    return new User({
      ...this.props,
      currentStreak,
      longestStreak: Math.max(this.props.longestStreak, currentStreak),
      lastActivityAt: now,
    });
  }

  toProps(): UserProps {
    return { ...this.props };
  }
}

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}
