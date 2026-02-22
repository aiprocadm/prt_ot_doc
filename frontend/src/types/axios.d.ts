export {};

declare module "axios" {
  export interface AxiosRequestConfig {
    _retry?: boolean;
  }
}
