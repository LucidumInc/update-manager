from jinja2 import Environment, FileSystemLoader

_jinja_env = Environment(loader=FileSystemLoader("tmplts"))


class BaseTemplateFormatter:

    @property
    def template_file(self) -> str:
        raise NotImplementedError

    @property
    def output_file(self) -> str:
        raise NotImplementedError

    def get_template_params(self):
        raise NotImplementedError


def format_template(formatter: BaseTemplateFormatter) -> None:
    template = _jinja_env.get_template(formatter.template_file)
    template.stream(**formatter.get_template_params()).dump(formatter.output_file)
