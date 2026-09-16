/**
 * Port for password hashing. Kept out of the domain/application code path's
 * concrete implementation (bcryptjs) so use cases stay framework/library
 * free and testable with a fake.
 */
export interface PasswordHasher {
  hash(plainText: string): Promise<string>;
  compare(plainText: string, hash: string): Promise<boolean>;
}
