export type PermissionCode =
  | 'templates.read'
  | 'templates.write'
  | 'documents.read'
  | 'documents.write'
  | 'files.read'
  | 'files.write'
  | 'jobs.manage'
  | 'audit.read';

export const hasPermission = (permissions: string[], permission: PermissionCode): boolean => {
  return permissions.includes(permission);
};
