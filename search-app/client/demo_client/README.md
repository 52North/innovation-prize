# Demo Client based on VueJS

## Requirements:

Install Node.js version 18.3 or higher

## Installation

Install the dependencies from within the client directory:

```bash
npm install
```

Start the app with
```bash
npm run dev
```

Open the client at http://localhost:5137.

The application will connect backend API http://localhost:8000 by default.
To connect a different backend, copy `sample.env` to `.env` and configure `VUE_APP_BACKEND_API_URL`.
If necessary to connect a backend which is not served samesite, make sure the backend [allows cross site requests](https://enable-cors.org/).
