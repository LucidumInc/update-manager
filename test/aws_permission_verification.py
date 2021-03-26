import yaml


class EnvironmentTest():

  def __init__(self):
    self.yaml_configuration_file = '/usr/lucidum/connector-aws_latest/external/settings.yml'
    self.accounts = self._get_accounts()
    self.cloudtrail_state = self._get_cloudtrail_state()
    self.cloudwatch_state = self._get_cloudwatch_state()
    self.config_state = self._get_config_state()
    self.dynamodb_state = self._get_dynamodb_state()
    self.ec2_state = self._get_ec2_state()
    self.ecs_state = self._get_ecs_state()
    self.eks_state = self._get_eks_state()
    self.elasticloadbalancing_state = self._get_elasticloadbalancing_state()
    self.guardduty_state = self._get_guardduty_state()
    self.iam_state = self._get_iam_state()
    self.inspector_state = self._get_inspector_state()
    self.kms_state = self._get_kms_state()
    self.lambda_state = self._get_lambda_state()
    self.logs_state = self._get_logs_state()
    self.organizations_state = self._get_organizations_state()
    self.pricing_state = self._get_pricing_state()
    self.route53_state = self._get_route53_state()
    self.s3_state = self._get_s3_state()
    self.securityhub_state = self._get_securityhub_state()
    self.ssm_state = self._get_ssm_state()
    self.sts_state = self._get_sts_state()
    self.tag_state = self._get_tag_state()

  def make_report(self):
    print("cloudtrail:")
    print("  ok:" + str(self.cloudtrail_state['ok']))
    print("  not-ok:" + str(self.cloudtrail_state['not-ok']))

    print("cloudwatch:")
    print("  ok:" + str(self.cloudwatch_state['ok']))
    print("  not-ok:" + str(self.cloudwatch_state['not-ok']))

    print("config:")
    print("  ok:" + str(self.config_state['ok']))
    print("  not-ok:" + str(self.config_state['not-ok']))

    print("dynamodb:")
    print("  ok:" + str(self.dynamodb_state['ok']))
    print("  not-ok:" + str(self.dynamodb_state['not-ok']))

    print("ec2:")
    print("  ok:" + str(self.ec2_state['ok']))
    print("  not-ok:" + str(self.ec2_state['not-ok']))

    print("ecs:")
    print("  ok:" + str(self.ecs_state['ok']))
    print("  not-ok:" + str(self.ecs_state['not-ok']))

    print("eks:")
    print("  ok:" + str(self.eks_state['ok']))
    print("  not-ok:" + str(self.eks_state['not-ok']))

    print("elasticloadbalancing")
    print("  ok:" + str(self.elasticloadbalancing_state['ok']))
    print("  not-ok:" + str(self.elasticloadbalancing_state['not-ok']))

    print("guardduty")
    print("  ok:" + str(self.guardduty_state['ok']))
    print("  not-ok:" + str(self.guardduty_state['not-ok']))

    print("iam:")
    print("  ok:" + str(self.iam_state['ok']))
    print("  not-ok:" + str(self.iam_state['not-ok']))

    print("inspector:")
    print("  ok:" + str(self.inspector_state['ok']))
    print("  not-ok:" + str(self.inspector_state['not-ok']))

    print("kms:")
    print("  ok:" + str(self.kms_state['ok']))
    print("  not-ok:" + str(self.kms_state['not-ok']))

    print("lambda:")
    print("  ok:" + str(self.lambda_state['ok']))
    print("  not-ok:" + str(self.lambda_state['not-ok']))

    print("logs:")
    print("  ok:" + str(self.logs_state['ok']))
    print("  not-ok:" + str(self.logs_state['not-ok']))

    print("organizations:")
    print("  ok:" + str(self.organizations_state['ok']))
    print("  not-ok:" + str(self.organizations_state['not-ok']))

    print("pricing:")
    print("  ok:" + str(self.pricing_state['ok']))
    print("  not-ok:" + str(self.pricing_state['not-ok']))

    print("route53:")
    print("  ok:" + str(self.route53_state['ok']))
    print("  not-ok:" + str(self.route53_state['not-ok']))

    print("s3:")
    print("  ok:" + str(self.s3_state['ok']))
    print("  not-ok:" + str(self.s3_state['not-ok']))

    print("securityhub:")
    print("  ok:" + str(self.securityhub_state['ok']))
    print("  not-ok:" + str(self.securityhub_state['not-ok']))

    print("ssm:")
    print("  ok:" + str(self.ssm_state['ok']))
    print("  not-ok:" + str(self.ssm_state['not-ok']))

    print("sts:")
    print("  ok:" + str(self.sts_state['ok']))
    print("  not-ok:" + str(self.sts_state['not-ok']))

    print("tag:")
    print("  ok:" + str(self.tag_state['ok']))
    print("  not-ok:" + str(self.tag_state['not-ok']))


  def _get_cloudtrail_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_cloudwatch_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_config_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_dynamodb_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_ec2_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_ecs_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_eks_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_elasticloadbalancing_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_guardduty_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_iam_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_inspector_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_kms_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_lambda_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_logs_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_organizations_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_pricing_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_route53_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_s3_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_securityhub_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_ssm_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_sts_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_tag_state(self):
    return { 'ok': self.accounts, 'not-ok': self.accounts }

  def _get_accounts(self):
    with open(self.yaml_configuration_file) as aws_yaml:
      accounts = yaml.load(aws_yaml, Loader=yaml.FullLoader)
    return accounts['global']['aws_server']['role_accounts']


if __name__ == '__main__':
  test = EnvironmentTest()
  test.make_report()
